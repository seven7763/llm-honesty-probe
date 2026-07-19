"""Probe framework: a probe is a callable ``run(endpoint, ctx) -> List[Signal]``.

Every probe must:
  * be read-only and side-effect free beyond issuing API calls;
  * degrade to an INCONCLUSIVE signal when a feature is unsupported or errors;
  * never place the API key anywhere near its output (use the redaction layer).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

from ..client import Endpoint
from ..signals import Signal
from .. import families


@dataclasses.dataclass
class ProbeContext:
    claimed_model: str
    repeats: int = 5
    max_tokens: int = 64
    temperature: float = 0.0
    # Optional reference endpoint for differential ("compare") signals.
    compare_endpoint: Optional[Endpoint] = None
    compare_model: Optional[str] = None
    # Tokenizer reference table (family -> {"deltas": {...}}), loaded from disk.
    tokenizer_reference: Dict[str, Any] = dataclasses.field(default_factory=dict)
    # Needle-recall context lengths (in approx characters).
    needle_lengths: List[int] = dataclasses.field(default_factory=lambda: [2000, 8000, 24000])
    # Free-form user config (custom probes / known answers).
    config: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def tokenizer_family(self) -> str:
        return families.tokenizer_family(self.claimed_model)


# Registry ---------------------------------------------------------------------
RunFn = Callable[[Endpoint, ProbeContext], List[Signal]]

_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register(name: str, description: str) -> Callable[[RunFn], RunFn]:
    def deco(fn: RunFn) -> RunFn:
        _REGISTRY[name] = {"run": fn, "description": description}
        return fn
    return deco


def available() -> List[str]:
    return sorted(_REGISTRY.keys())


def description(name: str) -> str:
    return _REGISTRY.get(name, {}).get("description", "")


def get(name: str) -> Optional[RunFn]:
    entry = _REGISTRY.get(name)
    return entry["run"] if entry else None


def load_builtin() -> None:
    """Import the built-in probe modules so their @register runs."""
    from . import identity, tokenizer, reasoning, needle, consistency  # noqa: F401
