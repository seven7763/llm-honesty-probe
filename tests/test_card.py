import json
import os
import unittest

from llm_honesty_probe import card as card_mod
from llm_honesty_probe import redaction
from llm_honesty_probe._mockserver import running_server
from llm_honesty_probe.client import Endpoint
from llm_honesty_probe.probes import ProbeContext, get, load_builtin

load_builtin()

_REF_PATH = os.path.join(os.path.dirname(__file__), "..", "llm_honesty_probe",
                         "data", "tokenizers.json")


def _reference():
    try:
        with open(_REF_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}


def _run(base_url, key="sk-test-not-real-000000", model="gpt-4o", **ctx_kw):
    ep = Endpoint(base_url=base_url, protocol="openai", api_key=key)
    ctx = ProbeContext(claimed_model=model, repeats=4,
                       tokenizer_reference=_reference(), **ctx_kw)
    signals = []
    for name in ["identity", "reasoning", "needle", "consistency", "tokenizer"]:
        signals.extend(get(name)(ep, ctx))
    return signals


def _meta(base_url, mode="single-endpoint", model="gpt-4o"):
    return {"base_url": base_url, "protocol": "openai", "claimed_model": model,
            "mode": mode, "probes": ["all"]}


class VerdictTest(unittest.TestCase):
    def test_honest_run_is_pass(self):
        with running_server(degrade=False) as base_url:
            signals = _run(base_url)
        card = card_mod.build_card(signals, _meta(base_url))
        self.assertEqual(card.verdict, card_mod.PASS)
        # The four headline rows are always present.
        self.assertEqual([r.key for r in card.rows],
                         ["tokenizer", "reasoning", "needle", "consistency"])

    def test_degraded_run_is_suspicious(self):
        with running_server(degrade=True) as base_url:
            signals = _run(base_url, needle_lengths=[2000, 8000])
        card = card_mod.build_card(signals, _meta(base_url))
        self.assertEqual(card.verdict, card_mod.SUSPICIOUS_V)


class RenderTest(unittest.TestCase):
    def test_all_formats_render(self):
        with running_server(degrade=True) as base_url:
            signals = _run(base_url, needle_lengths=[2000, 8000])
        card = card_mod.build_card(signals, _meta(base_url))
        for fmt in ("txt", "md", "svg", "html"):
            out = card_mod.render(card, fmt)
            self.assertTrue(out.strip(), "%s should be non-empty" % fmt)
            self.assertIn("SUSPICIOUS", out)
        svg = card_mod.render_svg(card)
        self.assertTrue(svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
        # The neutral daoxe signature (UTM/domain) rides on the card.
        self.assertIn("daoxe", card_mod.render_html(card))


class EndpointMaskingTest(unittest.TestCase):
    def test_endpoint_masked_by_default(self):
        meta = _meta("https://cheap-relay.example/v1")
        with running_server(degrade=False) as base_url:
            signals = _run(base_url)
        card = card_mod.build_card(signals, meta, show_endpoint=False)
        self.assertNotIn("cheap-relay.example", card.endpoint)
        self.assertNotIn("cheap-relay.example", card_mod.render_svg(card))

    def test_endpoint_shown_on_opt_in(self):
        meta = _meta("https://cheap-relay.example/v1")
        with running_server(degrade=False) as base_url:
            signals = _run(base_url)
        card = card_mod.build_card(signals, meta, show_endpoint=True)
        self.assertIn("cheap-relay.example", card.endpoint)


class CardKeySafetyTest(unittest.TestCase):
    def test_key_never_appears_in_any_card_format(self):
        secret = "sk-donotleak-card-abcdef1234567890"
        redaction.clear_secrets()
        with running_server(degrade=True) as base_url:
            signals = _run(base_url, key=secret, needle_lengths=[2000, 8000])
            card = card_mod.build_card(signals, _meta(base_url), show_endpoint=True)
            for fmt in ("txt", "md", "svg", "html"):
                self.assertNotIn(secret, card_mod.render(card, fmt))


if __name__ == "__main__":
    unittest.main()
