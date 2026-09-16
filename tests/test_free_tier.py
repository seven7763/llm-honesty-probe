"""Free-tier-awareness tests (v0.2.2).

Motivated by the 2026-09-16 free-group run: needle and the strict-format /
refusal tasks failed with shapes the probe conflated ("Request failed:
unknown", "outcomes: null"), so a reader could not tell apart

  (a) a quota / rate-limit / model-unavailable refusal by the endpoint tier,
  (b) a reasoning model eating the whole max_tokens budget (empty content,
      finish_reason = "length"), and
  (c) a genuine honesty signal.

All three must stay *inconclusive* — none may raise suspicion — but each must
be named honestly, and (a) gets a ``free-tier-limited`` tag on the card.

Fixtures are desensitised copies of real response bodies captured on
2026-09-15/16 (NewAPI-style 503 ``model_not_found`` / OpenAI-style 429
``insufficient_quota``).
"""

import unittest

from llm_honesty_probe import card as card_mod
from llm_honesty_probe._mockserver import running_server
from llm_honesty_probe.client import Endpoint, free_tier_limited
from llm_honesty_probe.probes import ProbeContext, get, load_builtin
from llm_honesty_probe.signals import SUSPICIOUS, INCONCLUSIVE

load_builtin()


def _run_needle_and_reasoning(base_url, model="glm-4.7-flash"):
    ep = Endpoint(base_url=base_url, protocol="openai", api_key="sk-test-not-real-000000")
    ctx = ProbeContext(claimed_model=model, repeats=2, needle_lengths=[2000, 8000])
    signals = []
    for name in ["needle", "reasoning"]:
        signals.extend(get(name)(ep, ctx))
    return signals


def _free_tier_tagged(signals):
    return [s for s in signals if "free-tier-limited" in getattr(s, "tags", [])]


class ClassifierTest(unittest.TestCase):
    """The identification table is deliberately conservative: known quota /
    rate-limit / model-unavailable bodies match; anything else does not."""

    def _err(self, status, body):
        ep = Endpoint(base_url="http://127.0.0.1:1/v1")  # never contacted
        from llm_honesty_probe.client import ChatResult
        return ChatResult(ok=False, http_status=status, latency_ms=1.0, error=body)

    def test_openai_quota_429_matches(self):
        r = self._err(429, 'HTTP 429: {"error": {"message": "You exceeded your current '
                           'quota, please check your plan and billing details", '
                           '"type": "insufficient_quota"}}')
        self.assertTrue(free_tier_limited(r))

    def test_newapi_no_channel_503_matches(self):
        # Desensitised 2026-09-16 capture: group-level "no available channel".
        r = self._err(503, 'HTTP 503: {"error":{"code":"model_not_found",'
                           '"message":"no available channel (distributor)",'
                           '"type":"new_api_error"}}')
        self.assertTrue(free_tier_limited(r))

    def test_chinese_no_channel_matches(self):
        r = self._err(503, "HTTP 503: 分组 X 下模型 Y 无可用渠道（distributor）")
        self.assertTrue(free_tier_limited(r))

    def test_bare_429_status_matches(self):
        r = self._err(429, "HTTP 429: <html>rate limited</html>")
        self.assertTrue(free_tier_limited(r))

    def test_unrelated_500_does_not_match(self):
        r = self._err(500, "HTTP 500: internal server error while loading weights")
        self.assertFalse(free_tier_limited(r))

    def test_network_error_does_not_match(self):
        r = self._err(0, "network error: timed out")
        self.assertFalse(free_tier_limited(r))

    def test_successful_response_never_matches(self):
        from llm_honesty_probe.client import ChatResult
        ok = ChatResult(ok=True, http_status=200, latency_ms=1.0, text="hi")
        self.assertFalse(free_tier_limited(ok))


class QuotaRefusalTest(unittest.TestCase):
    """A 429 quota wall on every call: inconclusive, never suspicious, tagged
    ``free-tier-limited``, with the error preserved in the evidence."""

    def test_needle_inconclusive_tagged_not_suspicious(self):
        with running_server(quota=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        needle = [s for s in signals if s.probe == "needle"]
        self.assertTrue(needle)
        for s in needle:
            self.assertNotEqual(s.verdict, SUSPICIOUS)
            self.assertEqual(s.verdict, INCONCLUSIVE)
        tagged = _free_tier_tagged(signals)
        self.assertTrue(any(s.probe == "needle" for s in tagged),
                        "needle should carry the free-tier-limited tag")
        # The raw error must be greppable in the evidence, not swallowed.
        ev = str(needle[0].evidence)
        self.assertIn("429", ev)

    def test_format_and_refusal_tagged(self):
        with running_server(quota=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        fmt = [s for s in signals if s.title == "Strict format following"]
        ref = [s for s in signals if s.title == "Refusal behavior"]
        self.assertTrue(fmt and ref)
        for s in fmt + ref:
            self.assertEqual(s.verdict, INCONCLUSIVE)
            self.assertNotEqual(s.verdict, SUSPICIOUS)
            self.assertIn("free-tier-limited", getattr(s, "tags", []))
        for s in fmt + ref:
            self.assertNotIn("unknown", s.detail)

    def test_card_shows_the_tag(self):
        with running_server(quota=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        meta = {"base_url": base_url, "protocol": "openai",
                "claimed_model": "glm-4.7-flash", "mode": "single-endpoint",
                "probes": ["needle", "reasoning"]}
        card = card_mod.build_card(signals, meta)
        for fmt in ("txt", "md", "svg", "html"):
            self.assertIn("free-tier-limited", card_mod.render(card, fmt),
                          "the tag must be visible on the %s card" % fmt)


class NoChannelRefusalTest(unittest.TestCase):
    """NewAPI-style 503 model_not_found (free group has no channel for the
    model): same treatment — inconclusive + tag, zero red flags."""

    def test_all_probes_inconclusive_tagged(self):
        with running_server(no_channel=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        self.assertFalse([s for s in signals if s.verdict == SUSPICIOUS])
        tagged = _free_tier_tagged(signals)
        self.assertTrue(any(s.probe == "needle" for s in tagged))
        self.assertTrue(any(s.title == "Strict format following" for s in tagged))
        self.assertTrue(any(s.title == "Refusal behavior" for s in tagged))


class BudgetStarvedWordingTest(unittest.TestCase):
    """The 2026-09-16 'Request failed: unknown' mystery: ok=True + empty +
    finish_reason=length is budget starvation, NOT a request failure. The
    verdict stays inconclusive but the wording must say so, and no
    free-tier tag may appear."""

    def test_format_refusal_says_budget_not_unknown(self):
        with running_server(reasoning=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        fmt = [s for s in signals if s.title == "Strict format following"]
        ref = [s for s in signals if s.title == "Refusal behavior"]
        self.assertTrue(fmt and ref)
        for s in fmt + ref:
            self.assertEqual(s.verdict, INCONCLUSIVE)
            self.assertNotIn("unknown", s.detail)
            self.assertIn("budget", s.detail.lower())
            self.assertNotIn("free-tier-limited", getattr(s, "tags", []))

    def test_needle_names_the_starvation(self):
        with running_server(reasoning=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        needle = [s for s in signals if s.probe == "needle"]
        self.assertTrue(needle)
        for s in needle:
            self.assertNotEqual(s.verdict, SUSPICIOUS)
            self.assertIn("budget", s.detail.lower())
            self.assertNotIn("free-tier-limited", getattr(s, "tags", []))


class UntaggedOnErrorTest(unittest.TestCase):
    """Specificity: an unrecognised 500 must stay plain inconclusive — the
    conservative table must not hand out the free-tier tag for everything."""

    def test_generic_500_no_tag(self):
        with running_server(flaky_500=True) as base_url:
            signals = _run_needle_and_reasoning(base_url)
        self.assertFalse(_free_tier_tagged(signals),
                         "unrecognised errors must not be tagged free-tier-limited")
        self.assertFalse([s for s in signals if s.verdict == SUSPICIOUS])
        # Still recorded, though.
        needle = [s for s in signals if s.probe == "needle"][0]
        self.assertIn("500", str(needle.evidence))


if __name__ == "__main__":
    unittest.main()
