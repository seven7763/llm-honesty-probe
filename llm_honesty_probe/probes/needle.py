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

from typing import List, Optional

from ..client import Endpoint, budget_starved
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


def _ask(endpoint: Endpoint, model: str, approx_chars: int) -> Optional[bool]:
    context = _build_context(approx_chars)
    prompt = (context +
              "\n\nQuestion: exactly one line above states a secret passphrase. "
              "Reply with ONLY that passphrase and nothing else.")
    r = endpoint.chat(model=model,
                      messages=[{"role": "user", "content": prompt}],
                      temperature=0.0, max_tokens=256)
    if not r.ok or budget_starved(r):
        return None
    return _PASSPHRASE.lower() in (r.text or "").lower()


@register("needle", "Hide a passphrase in long context and check recall across lengths (catches truncation).")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    lengths = sorted(set(ctx.needle_lengths))
    outcomes = {}
    first_fail = None
    for n in lengths:
        ok = _ask(endpoint, ctx.claimed_model, n)
        outcomes[n] = ok
        if ok is False and first_fail is None:
            first_fail = n

    evidence = {"outcomes": outcomes, "lengths_chars": lengths}

    graded = [n for n, ok in outcomes.items() if ok is not None]
    if not graded:
        return [inconclusive("needle", "Long-context recall",
                             "All needle requests errored (context may exceed a hard limit).",
                             evidence)]

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
