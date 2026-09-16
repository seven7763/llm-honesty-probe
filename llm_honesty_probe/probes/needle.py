"""Long-context needle-in-a-haystack recall.

We generate deterministic filler text, hide a unique passphrase in the middle,
and ask the endpoint to read it back. Because *we* place the needle, the correct
answer is always known — no external reference required. A model that recalls the
needle at short context but loses it at longer context is a classic signature of
silent context truncation (a relay quietly capping your window to save tokens).

Cost note: long contexts cost input tokens. Lengths are configurable and default
to modest sizes; see the README's budget note.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..client import Endpoint, budget_starved, free_tier_limited
from ..signals import Signal, CONSISTENT, SUSPICIOUS, LOW, MEDIUM, inconclusive
from . import register, ProbeContext

_PASSPHRASE = "SWORDFISH-7492-ALPHA"
_NEEDLE = "IMPORTANT: the secret passphrase is %s. Remember it." % _PASSPHRASE


def _filler(approx_chars: int) -> str:
    lines = []
    total = 0
    i = 1
    while total < approx_chars:
        line = ("Line %05d: the archive holds many unremarkable maintenance records "
                "that are safe to skim past.\n" % i)
        lines.append(line)
        total += len(line)
        i += 1
    return lines


def _build_context(approx_chars: int) -> str:
    lines = _filler(approx_chars)
    mid = len(lines) // 2
    lines.insert(mid, _NEEDLE + "\n")
    return "".join(lines)


def _ask(endpoint: Endpoint, model: str, approx_chars: int
         ) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
    """Returns (recalled?, failure_reason, error_excerpt). failure_reason is
    None when the request graded; otherwise 'quota' / 'budget' / 'error'."""
    context = _build_context(approx_chars)
    prompt = (context +
              "\n\nQuestion: exactly one line above states a secret passphrase. "
              "Reply with ONLY that passphrase and nothing else.")
    r = endpoint.chat(model=model,
                      messages=[{"role": "user", "content": prompt}],
                      temperature=0.0, max_tokens=256)
    if not r.ok:
        return None, ("quota" if free_tier_limited(r) else "error"), r.error
    if budget_starved(r):
        return None, "budget", None
    return _PASSPHRASE.lower() in (r.text or "").lower(), None, None


@register("needle", "Hide a passphrase in long context and check recall across lengths (catches truncation).")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    lengths = sorted(set(ctx.needle_lengths))
    outcomes = {}
    reasons = {}
    first_error = None
    first_fail = None
    for n in lengths:
        ok, reason, err = _ask(endpoint, ctx.claimed_model, n)
        outcomes[n] = ok
        if reason is not None:
            reasons[n] = reason
            if first_error is None and err:
                first_error = err[:200]
        if ok is False and first_fail is None:
            first_fail = n

    evidence = {"outcomes": outcomes, "lengths_chars": lengths}
    if reasons:
        evidence["failure_reasons"] = reasons
    if first_error:
        evidence["first_error"] = first_error

    graded = [n for n, ok in outcomes.items() if ok is not None]
    if not graded:
        # "The probe couldn't run" must not read as "the endpoint is bad".
        # Name the shape we saw: quota refusal, budget starvation, or generic
        # errors (which may still be a context cap — say so, but as a hint).
        reason_set = set(reasons.values())
        if "quota" in reason_set:
            # Kept <=72 chars so the card shows this line, not a fallback.
            tags = ["free-tier-limited"]
            detail = ("All needle calls hit a quota / model-unavailable refusal "
                      "(tier limit).")
        elif reason_set == {"budget"}:
            tags = []
            detail = "All needle replies were empty: thinking ate the max_tokens budget."
        else:
            tags = []
            detail = "All needle requests errored (context may exceed a hard limit)."
        return [inconclusive("needle", "Long-context recall", detail, evidence, tags=tags)]

    if first_fail is None:
        return [Signal("needle", "Long-context recall", CONSISTENT, MEDIUM,
                       "Recalled the needle at all tested lengths (up to ~%d chars)." % max(graded),
                       evidence)]

    # Failing at a small context is a strong truncation/capability signal;
    # failing only at very large context might just be the model's real limit.
    if first_fail <= 4000:
        return [Signal("needle", "Long-context recall", SUSPICIOUS, MEDIUM,
                       "Lost the needle at only ~%d chars; any full model handles that. "
                       "Suggests truncation or a weaker model." % first_fail, evidence)]
    return [Signal("needle", "Long-context recall", SUSPICIOUS, LOW,
                   "Recall broke at ~%d chars. Could be silent truncation or the model's real "
                   "context limit; diff against the official endpoint to disambiguate." % first_fail,
                   evidence)]
