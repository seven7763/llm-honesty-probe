"""Tokenizer fingerprint probe.

Idea: different model families use different tokenizers, and the tokenizer leaks
through the ``usage.prompt_tokens`` the server reports. For a battery of crafted
strings (digit runs, whitespace, CJK, emoji, code, ...), the *number of tokens*
each string costs is a fingerprint of the tokenizer.

To cancel the per-request chat-template overhead (role tokens, etc.), we measure
a delta: tokens(anchor + probe) - tokens(anchor). The resulting vector is close
to the raw token count of each probe string and is comparable across requests.

Two ways to read it:
  * ``--compare`` (best): diff the vector against a reference endpoint serving the
    same model id. Different vector => different tokenizer => almost certainly a
    different model/family. Reference-free and high confidence.
  * single endpoint: classify the vector against a shipped reference table of
    known tokenizers (currently OpenAI's cl100k_base / o200k_base via tiktoken).
    If the claim's family has no public reference (Claude, Gemini, ...), we say
    "inconclusive, use --compare" instead of guessing.

Honest caveats: some providers don't return usage, estimate it, or bill with
quirks; a single junction merge can shift a delta by 1. We therefore compare
vectors with a tolerance and never decide a lie from tokens alone.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..client import Endpoint, ChatResult
from ..signals import Signal, CONSISTENT, SUSPICIOUS, LOW, MEDIUM, HIGH, inconclusive
from .. import families
from . import register, ProbeContext

ANCHOR = "."

# (id, string). Order matters: it defines the fingerprint vector.
PROBE_STRINGS: List[Tuple[str, str]] = [
    ("digits", "1234567890" * 6),
    ("spaces", " " * 40),
    ("tabs", "\t" * 20),
    ("word_rep", "banana " * 20),
    ("cjk", "\u4f60\u597d\u4e16\u754c" * 12),
    ("emoji", "\U0001f600" * 16),
    ("accents", "caf\u00e9 r\u00e9sum\u00e9 na\u00efve Stra\u00dfe \u00der" * 3),
    ("code", "def f(x):\n    return x * x\n" * 4),
    ("url", "https://example.com/a/b?q=1&r=2 " * 4),
    ("mixed", "AbC123_xyz-\u6d4b\u8bd5-\U0001f680-END " * 5),
]

# L1 distance below this (summed over the vector) counts as a match.
MATCH_TOLERANCE = 3


def _measure_vector(endpoint: Endpoint, model: str) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
    """Return (delta-vector, error). None vector if usage isn't available."""
    base = endpoint.chat(model=model, messages=[{"role": "user", "content": ANCHOR}],
                         temperature=0.0, max_tokens=1)
    if not base.ok:
        return None, base.error or "anchor request failed"
    if base.prompt_tokens is None:
        return None, "server did not report usage.prompt_tokens"
    t0 = base.prompt_tokens
    vec: Dict[str, int] = {}
    for pid, s in PROBE_STRINGS:
        r = endpoint.chat(model=model,
                          messages=[{"role": "user", "content": ANCHOR + s}],
                          temperature=0.0, max_tokens=1)
        if not r.ok or r.prompt_tokens is None:
            return None, r.error or "missing usage on probe %r" % pid
        vec[pid] = int(r.prompt_tokens) - int(t0)
    return vec, None


def _l1(a: Dict[str, int], b: Dict[str, int]) -> int:
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)


def _ref_vector(ctx: ProbeContext, family: str) -> Optional[Dict[str, int]]:
    fam = ctx.tokenizer_reference.get("families", {}).get(family)
    if not fam:
        return None
    deltas = fam.get("deltas")
    if not isinstance(deltas, dict) or not deltas:
        return None
    return {k: int(v) for k, v in deltas.items()}


@register("tokenizer", "Fingerprint the tokenizer via usage.prompt_tokens; compare vs reference or a second endpoint.")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    vec, err = _measure_vector(endpoint, ctx.claimed_model)
    if vec is None:
        return [inconclusive("tokenizer", "Tokenizer fingerprint",
                             "Can't fingerprint tokenizer: %s." % err)]

    evidence = {"observed_vector": vec}

    # --- Best path: differential comparison against a reference endpoint. ---
    if ctx.compare_endpoint is not None:
        cmp_model = ctx.compare_model or ctx.claimed_model
        ref_vec, ref_err = _measure_vector(ctx.compare_endpoint, cmp_model)
        if ref_vec is None:
            evidence["compare_error"] = ref_err
        else:
            dist = _l1(vec, ref_vec)
            evidence["reference_vector"] = ref_vec
            evidence["l1_distance"] = dist
            if dist <= MATCH_TOLERANCE:
                return [Signal("tokenizer", "Tokenizer fingerprint (vs reference endpoint)",
                               CONSISTENT, HIGH,
                               "Tokenizer matches the reference endpoint (L1=%d)." % dist,
                               evidence)]
            return [Signal("tokenizer", "Tokenizer fingerprint (vs reference endpoint)",
                           SUSPICIOUS, HIGH,
                           "Tokenizer differs from the reference endpoint serving the same "
                           "model id (L1=%d) -> different model/family likely." % dist,
                           evidence)]

    # --- Single endpoint: classify against the shipped reference table. ---
    claimed_family = ctx.tokenizer_family
    evidence["claimed_family"] = claimed_family

    calibratable = {f: _ref_vector(ctx, f) for f in families.CALIBRATABLE}
    calibratable = {f: v for f, v in calibratable.items() if v is not None}

    if not calibratable:
        return [inconclusive("tokenizer", "Tokenizer fingerprint",
                             "No tokenizer reference is installed. Run scripts/build_reference.py "
                             "or use --compare against a trusted endpoint.", evidence)]

    distances = {f: _l1(vec, ref) for f, ref in calibratable.items()}
    best_family = min(distances, key=distances.get)
    evidence["distances"] = distances
    evidence["best_match"] = best_family

    if claimed_family not in families.CALIBRATABLE:
        note = ("Best structural match is %s (L1=%d), but there is no public "
                "reference for the claimed family '%s', so this isn't a verdict. "
                "Use --compare against the official endpoint." %
                (best_family, distances[best_family], claimed_family))
        return [inconclusive("tokenizer", "Tokenizer fingerprint", note, evidence)]

    claimed_dist = distances[claimed_family]
    best_dist = distances[best_family]

    if claimed_dist <= MATCH_TOLERANCE and best_family == claimed_family:
        return [Signal("tokenizer", "Tokenizer fingerprint", CONSISTENT, MEDIUM,
                       "Token counts match the %s tokenizer implied by the claim (L1=%d)."
                       % (claimed_family, claimed_dist), evidence)]

    if best_family != claimed_family and (claimed_dist - best_dist) > MATCH_TOLERANCE:
        return [Signal("tokenizer", "Tokenizer fingerprint", SUSPICIOUS, MEDIUM,
                       "Token counts match %s (L1=%d) better than the claimed %s (L1=%d)."
                       % (best_family, best_dist, claimed_family, claimed_dist), evidence)]

    return [inconclusive("tokenizer", "Tokenizer fingerprint",
                         "Token counts don't cleanly match any installed reference "
                         "(closest %s, L1=%d). Provider token accounting may differ." %
                         (best_family, best_dist), evidence)]
