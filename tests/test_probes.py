import json
import os
import unittest

from llm_honesty_probe import redaction
from llm_honesty_probe._mockserver import running_server
from llm_honesty_probe.client import Endpoint
from llm_honesty_probe.probes import ProbeContext, get, load_builtin
from llm_honesty_probe.probes import tokenizer as tok
from llm_honesty_probe.signals import SUSPICIOUS, CONSISTENT, INCONCLUSIVE

load_builtin()

_REF_PATH = os.path.join(os.path.dirname(__file__), "..", "llm_honesty_probe",
                         "data", "tokenizers.json")


def _reference():
    try:
        with open(_REF_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}


def _run_all(base_url, model="gpt-4o", **ctx_kw):
    ep = Endpoint(base_url=base_url, protocol="openai", api_key="sk-test-not-real-000000")
    ctx = ProbeContext(claimed_model=model, repeats=4,
                       tokenizer_reference=_reference(), **ctx_kw)
    signals = []
    for name in ["identity", "reasoning", "needle", "consistency", "tokenizer"]:
        signals.extend(get(name)(ep, ctx))
    return signals


def _by_probe(signals, probe):
    return [s for s in signals if s.probe == probe]


class HonestRunTest(unittest.TestCase):
    def test_no_medium_or_high_suspicion_on_honest_server(self):
        with running_server(degrade=False) as base_url:
            signals = _run_all(base_url)
        strong = [s for s in signals if s.verdict == SUSPICIOUS
                  and s.confidence in ("medium", "high")]
        self.assertEqual(strong, [], "honest server should raise no strong suspicion")

    def test_needle_and_reasoning_consistent_when_honest(self):
        with running_server(degrade=False) as base_url:
            signals = _run_all(base_url)
        self.assertTrue(any(s.verdict == CONSISTENT for s in _by_probe(signals, "needle")))
        self.assertTrue(any(s.verdict == CONSISTENT for s in _by_probe(signals, "reasoning")))


class DegradedRunTest(unittest.TestCase):
    def test_reasoning_flags_a_downgraded_server(self):
        with running_server(degrade=True) as base_url:
            signals = _run_all(base_url)
        floor = [s for s in _by_probe(signals, "reasoning")
                 if s.title.startswith("Capability floor")]
        self.assertTrue(floor and floor[0].verdict == SUSPICIOUS)

    def test_needle_flags_context_truncation(self):
        with running_server(degrade=True) as base_url:
            signals = _run_all(base_url, needle_lengths=[2000, 8000])
        self.assertTrue(any(s.verdict == SUSPICIOUS for s in _by_probe(signals, "needle")))


class CompareTokenizerTest(unittest.TestCase):
    def test_same_accounting_matches(self):
        with running_server(char_per_token=4) as a, running_server(char_per_token=4) as b:
            ep_a = Endpoint(base_url=a, api_key="sk-a-000000000000")
            ep_b = Endpoint(base_url=b, api_key="sk-b-000000000000")
            ctx = ProbeContext(claimed_model="gpt-4o", compare_endpoint=ep_b,
                               compare_model="gpt-4o", tokenizer_reference=_reference())
            sigs = tok.run(ep_a, ctx)
        self.assertEqual(sigs[0].verdict, CONSISTENT)

    def test_different_tokenizer_is_flagged(self):
        with running_server(char_per_token=4) as a, running_server(char_per_token=8) as b:
            ep_a = Endpoint(base_url=a, api_key="sk-a-000000000000")
            ep_b = Endpoint(base_url=b, api_key="sk-b-000000000000")
            ctx = ProbeContext(claimed_model="gpt-4o", compare_endpoint=ep_b,
                               compare_model="gpt-4o", tokenizer_reference=_reference())
            sigs = tok.run(ep_a, ctx)
        self.assertEqual(sigs[0].verdict, SUSPICIOUS)


class KeySafetyTest(unittest.TestCase):
    def test_key_never_appears_in_rendered_output(self):
        from llm_honesty_probe import report
        secret = "sk-donotleak-abcdef1234567890"
        redaction.clear_secrets()
        with running_server(degrade=False) as base_url:
            ep = Endpoint(base_url=base_url, api_key=secret)
            ctx = ProbeContext(claimed_model="gpt-4o", repeats=3,
                               tokenizer_reference=_reference())
            signals = []
            for name in ["identity", "reasoning", "consistency", "tokenizer"]:
                signals.extend(get(name)(ep, ctx))
            meta = {"base_url": base_url, "protocol": "openai",
                    "claimed_model": "gpt-4o", "mode": "test", "probes": ["all"]}
            text = report.render_text(signals, meta)
            js = report.render_json(signals, meta)
        self.assertNotIn(secret, text)
        self.assertNotIn(secret, js)

    def test_cli_has_no_key_flag(self):
        from llm_honesty_probe.cli import build_parser
        actions = " ".join(str(a.option_strings) for a in build_parser()._actions)
        self.assertNotIn("--key", actions)
        self.assertIn("--api-key-env", actions)


if __name__ == "__main__":
    unittest.main()


class ReasoningBudgetFalsePositiveTest(unittest.TestCase):
    """A reasoning model that spends the whole output budget on hidden thinking
    returns empty content with finish_reason='length'. That is a property of the
    caller's max_tokens, NOT dishonesty — probes must degrade to inconclusive and
    never raise suspicion."""

    def test_needle_not_falsely_suspicious(self):
        with running_server(reasoning=True) as base_url:
            signals = _run_all(base_url, needle_lengths=[2000, 8000])
        needle = _by_probe(signals, "needle")
        self.assertFalse([s for s in needle if s.verdict == SUSPICIOUS],
                         "reasoning-budget starvation must not flag the needle probe")

    def test_reasoning_floor_not_falsely_suspicious(self):
        with running_server(reasoning=True) as base_url:
            signals = _run_all(base_url)
        floor = [s for s in _by_probe(signals, "reasoning")
                 if s.title.startswith("Capability floor")]
        self.assertFalse([s for s in floor if s.verdict == SUSPICIOUS],
                         "reasoning-budget starvation must not flag the capability floor")
