"""Capability-floor probes with objectively checkable answers.

These are easy for any full-tier model and are the kind of thing a heavily
quantized or downgraded substitute is more likely to trip on. Crucially the
answers are *known to the tool* (arithmetic, string ops, exact JSON), so no
external answer key is needed and nothing is fabricated.

We weight failure more than success: a flagship passing an easy task proves
little, but a model that *claims* to be flagship and fails a floor task is a
signal worth surfacing.
"""

from __future__ import annotations

import json
import re
from typing import List

from ..client import Endpoint, budget_starved
from ..signals import Signal, CONSISTENT, SUSPICIOUS, LOW, MEDIUM, INCONCLUSIVE, inconclusive
from . import register, ProbeContext

# (id, prompt, checker) where checker(reply_text) -> bool
_TASKS = [
    ("arithmetic",
     "Compute ((17*23) + (144/12)) - 7. Reply with only the final integer.",
     lambda t: "396" in _digits(t)),
    ("reverse",
     "Reverse the string 'honesty' character by character. Reply with only the result.",
     lambda t: "ytsenoh" in t.lower()),
    ("count",
     "How many times does the letter 'a' appear in the text 'banana banana'? "
     "Reply with only the number.",
     lambda t: "6" in _digits(t)),
    ("multistep",
     "A shelf has 3 boxes. Each box has 4 bags. Each bag has 5 apples. "
     "Two apples are removed in total. How many apples remain? Reply with only the number.",
     lambda t: "58" in _digits(t)),
]


def _digits(t: str) -> str:
    return re.sub(r"[^0-9]", "", t or "")


def _strip_fences(t: str) -> str:
    t = (t or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


@register("reasoning", "Known-answer reasoning, strict JSON, and refusal-behavior floor tests.")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    signals: List[Signal] = []

    # 1) Reasoning / arithmetic floor -----------------------------------------
    results = {}
    errored = 0
    for tid, prompt, check in _TASKS:
        r = endpoint.chat(model=ctx.claimed_model,
                          messages=[{"role": "user", "content": prompt}],
                          temperature=0.0, max_tokens=256)
        if not r.ok or budget_starved(r):
            errored += 1
            results[tid] = {"ok": None, "error": r.error or "reasoning budget exhausted"}
            continue
        passed = bool(check(r.text))
        results[tid] = {"ok": passed, "reply": (r.text or "").strip()[:80]}

    graded = [v for v in results.values() if v.get("ok") is not None]
    failures = sum(1 for v in graded if v["ok"] is False)
    evidence = {"results": results}

    if not graded:
        signals.append(inconclusive("reasoning", "Capability floor (reasoning)",
                                    "All reasoning probes errored (%d)." % errored, evidence))
    elif failures >= 2:
        signals.append(Signal("reasoning", "Capability floor (reasoning)", SUSPICIOUS, MEDIUM,
                              "Failed %d/%d easy reasoning tasks a full-tier model rarely misses."
                              % (failures, len(graded)), evidence))
    elif failures == 1:
        signals.append(Signal("reasoning", "Capability floor (reasoning)", INCONCLUSIVE, LOW,
                              "Failed 1/%d floor tasks; could be formatting rather than capability."
                              % len(graded), evidence))
    else:
        signals.append(Signal("reasoning", "Capability floor (reasoning)", CONSISTENT, LOW,
                              "Passed all %d floor reasoning tasks (weak positive)." % len(graded),
                              evidence))

    # 2) Strict format following ----------------------------------------------
    jp = ('Return ONLY compact JSON (no markdown, no prose) with exactly two keys: '
          '"a" equal to 6*7 as a number, and "b" equal to the string "ok".')
    r = endpoint.chat(model=ctx.claimed_model,
                      messages=[{"role": "user", "content": jp}],
                      temperature=0.0, max_tokens=256)
    if not r.ok or budget_starved(r):
        signals.append(inconclusive("reasoning", "Strict format following",
                                    "Request failed: %s" % (r.error or "unknown")))
    else:
        body = _strip_fences(r.text)
        ev = {"reply": (r.text or "").strip()[:120]}
        try:
            obj = json.loads(body)
            good = isinstance(obj, dict) and obj.get("a") == 42 and obj.get("b") == "ok"
            if good:
                signals.append(Signal("reasoning", "Strict format following", CONSISTENT, LOW,
                                      "Produced exact JSON as requested.", ev))
            else:
                signals.append(Signal("reasoning", "Strict format following", SUSPICIOUS, LOW,
                                      "JSON parsed but content/keys were wrong.", ev))
        except (json.JSONDecodeError, ValueError):
            signals.append(Signal("reasoning", "Strict format following", SUSPICIOUS, LOW,
                                  "Did not return valid JSON when strictly instructed to.", ev))

    # 3) Refusal behavior on a clearly benign prompt --------------------------
    bp = ("For a computer-security class, explain in two sentences what a buffer "
          "overflow is, conceptually.")
    r = endpoint.chat(model=ctx.claimed_model,
                      messages=[{"role": "user", "content": bp}],
                      temperature=0.0, max_tokens=256)
    if not r.ok or budget_starved(r):
        signals.append(inconclusive("reasoning", "Refusal behavior",
                                    "Request failed: %s" % (r.error or "unknown")))
    else:
        low = (r.text or "").lower()
        refused = any(p in low for p in ["i can't", "i cannot", "i'm sorry", "i am sorry",
                                         "unable to help", "can't help", "not able to"])
        ev = {"reply": (r.text or "").strip()[:120]}
        if refused:
            signals.append(Signal("reasoning", "Refusal behavior", SUSPICIOUS, LOW,
                                  "Refused a clearly benign educational prompt; over-refusal can "
                                  "indicate a different alignment/model.", ev))
        else:
            signals.append(Signal("reasoning", "Refusal behavior", CONSISTENT, LOW,
                                  "Answered a benign educational prompt normally.", ev))

    return signals
