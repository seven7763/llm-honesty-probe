"""Key-safety layer.

Design goal: it must be *impossible* for an API key to appear in this tool's
output, on disk, or in an error message. We achieve that two ways:

1. The key is only ever read from an environment variable (never a CLI flag, so
   it cannot leak via shell history, ``ps``/argv, or a saved command).
2. Every string that could reach the screen, a file, or a log is passed through
   :func:`redact`, which scrubs (a) any secret we were explicitly handed and
   (b) anything matching a known key/authorization shape.

There is intentionally no code path that prints ``api_key`` or an ``Authorization``
header. If you are auditing this project, this is the file to read first.
"""

from __future__ import annotations

import re
from typing import Iterable, Set

_PLACEHOLDER = "***REDACTED***"

# Secrets we were explicitly given (the exact key string, etc.). We keep only
# these exact values so we can scrub them verbatim wherever they might surface.
_KNOWN_SECRETS: Set[str] = set()

# Best-effort structural patterns for common key / auth shapes, so we redact even
# secrets we were never handed (e.g. a key echoed back inside a provider error).
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"),          # Anthropic
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),              # OpenAI & lookalikes
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),    # Authorization: Bearer ...
    re.compile(r"(?i)x-api-key['\"\s:=]+[A-Za-z0-9._\-]{8,}"),
]


def register_secret(value: str) -> None:
    """Register an exact secret string to be scrubbed from all future output."""
    if value and isinstance(value, str) and len(value) >= 4:
        _KNOWN_SECRETS.add(value)


def clear_secrets() -> None:
    """Forget all registered secrets (used by tests)."""
    _KNOWN_SECRETS.clear()


def redact(text: str) -> str:
    """Return ``text`` with every known secret and key-shaped token removed."""
    if not text:
        return text
    out = str(text)
    # Scrub the longest known secrets first so partial overlaps can't leak a tail.
    for secret in sorted(_KNOWN_SECRETS, key=len, reverse=True):
        if secret:
            out = out.replace(secret, _PLACEHOLDER)
    for pattern in _PATTERNS:
        out = pattern.sub(_PLACEHOLDER, out)
    return out


def redact_all(values: Iterable[str]) -> list:
    return [redact(v) for v in values]
