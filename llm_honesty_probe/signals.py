"""The unit of output: a :class:`Signal`.

A signal is a single heuristic observation with an explicit verdict and an honest
confidence. We deliberately never emit a boolean "genuine / fake" — the tool's
whole contract is that it reports signals, and a human draws the conclusion.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

# Verdicts. Kept coarse on purpose.
CONSISTENT = "consistent"      # behaviour is compatible with the claimed model
SUSPICIOUS = "suspicious"      # behaviour is hard to explain if the claim is true
INCONCLUSIVE = "inconclusive"  # not enough signal (unsupported feature, error, noise)

# Confidence. Even our strongest signal is not proof, so "high" is used sparingly.
LOW = "low"
MEDIUM = "medium"
HIGH = "high"

_VERDICT_MARK = {
    CONSISTENT: "OK ",
    SUSPICIOUS: "!! ",
    INCONCLUSIVE: "-- ",
}


@dataclasses.dataclass
class Signal:
    probe: str                 # which probe produced this (e.g. "tokenizer")
    title: str                 # short human title
    verdict: str               # one of CONSISTENT / SUSPICIOUS / INCONCLUSIVE
    confidence: str            # one of LOW / MEDIUM / HIGH
    detail: str                # one-line, human-readable explanation
    evidence: Dict[str, Any] = dataclasses.field(default_factory=dict)
    # Machine-readable labels explaining *why* the probe couldn't grade
    # (e.g. "free-tier-limited"). Shown verbatim on the verdict card; they
    # never change the verdict themselves.
    tags: List[str] = dataclasses.field(default_factory=list)

    def mark(self) -> str:
        return _VERDICT_MARK.get(self.verdict, "?? ")

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "probe": self.probe,
            "title": self.title,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "detail": self.detail,
            "evidence": self.evidence,
        }
        if self.tags:
            d["tags"] = list(self.tags)
        return d


def inconclusive(probe: str, title: str, detail: str,
                 evidence: Optional[Dict[str, Any]] = None,
                 tags: Optional[List[str]] = None) -> Signal:
    """Convenience for the very common "we couldn't tell" case."""
    return Signal(probe=probe, title=title, verdict=INCONCLUSIVE,
                  confidence=LOW, detail=detail, evidence=evidence or {},
                  tags=list(tags or []))
