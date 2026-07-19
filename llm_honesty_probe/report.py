"""Rendering: turn a list of Signals into human text or JSON.

The renderer is where we repeat the tool's core promise in every single run:
the output is a set of heuristic signals, not proof. That line is not optional
copy — it's the honest contract of the tool.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import __version__
from .redaction import redact
from .signals import Signal, CONSISTENT, SUSPICIOUS, INCONCLUSIVE

DISCLAIMER = "heuristic signals, NOT proof"
_REMINDER = ("Reminder: these are heuristic signals, not cryptographic proof. "
             "A calm run is reassuring, not a guarantee; a flag is a reason to "
             "diff against the official endpoint, not a conviction. See LIMITATIONS.")


def summarize(signals: List[Signal]) -> Dict[str, int]:
    out = {CONSISTENT: 0, SUSPICIOUS: 0, INCONCLUSIVE: 0}
    for s in signals:
        out[s.verdict] = out.get(s.verdict, 0) + 1
    return out


def _headline(signals: List[Signal]) -> str:
    strong = [s for s in signals if s.verdict == SUSPICIOUS and s.confidence in ("medium", "high")]
    weak = [s for s in signals if s.verdict == SUSPICIOUS]
    if strong:
        return "Some signals warrant a closer look (diff against the official endpoint)."
    if weak:
        return "Only low-confidence flags; likely noise, but worth a second run."
    return "No strong red flags in this run (still not a guarantee)."


def render_text(signals: List[Signal], meta: Dict[str, Any]) -> str:
    lines = []
    lines.append("llm-honesty-probe v%s  \u2014  %s" % (__version__, DISCLAIMER))
    lines.append("Endpoint : %s (%s)   claimed model: %s"
                 % (redact(meta.get("base_url", "")), meta.get("protocol", ""),
                    redact(meta.get("claimed_model", ""))))
    if meta.get("compare_base_url"):
        lines.append("Reference: %s (%s)   model: %s"
                     % (redact(meta["compare_base_url"]), meta.get("compare_protocol", ""),
                        redact(meta.get("compare_model", ""))))
    lines.append("Mode     : %s" % meta.get("mode", "single-endpoint"))
    lines.append("Probes   : %s" % ", ".join(meta.get("probes", [])))
    lines.append("-" * 66)

    for s in signals:
        lines.append("[%s] %-11s %-34s (%s)"
                     % (s.mark().strip(), s.probe, s.title, s.confidence))
        lines.append("     " + redact(s.detail))
    lines.append("-" * 66)

    c = summarize(signals)
    lines.append("Summary: %d consistent \u00b7 %d suspicious \u00b7 %d inconclusive"
                 % (c[CONSISTENT], c[SUSPICIOUS], c[INCONCLUSIVE]))
    lines.append(_headline(signals))
    lines.append(_REMINDER)
    return "\n".join(lines)


def render_json(signals: List[Signal], meta: Dict[str, Any]) -> str:
    payload = {
        "tool": "llm-honesty-probe",
        "version": __version__,
        "disclaimer": "Heuristic signals, not proof. See LIMITATIONS in the README.",
        "meta": {k: redact(str(v)) if isinstance(v, str) else v for k, v in meta.items()},
        "summary": summarize(signals),
        "headline": _headline(signals),
        "signals": [json.loads(redact(json.dumps(s.to_dict()))) for s in signals],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
