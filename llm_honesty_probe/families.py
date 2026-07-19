"""Best-effort mapping from a *claimed* model id to what we can expect from it.

This is intentionally conservative. If we don't recognise a model, we say so and
the affected probes return "inconclusive" rather than guessing. The mapping is
only used to pick expectations (e.g. which tokenizer a claim implies); it never
by itself decides that an endpoint is lying.
"""

from __future__ import annotations

from typing import Dict, Optional

# Tokenizer family keys used by reference/tokenizers.json and the tokenizer probe.
TK_O200K = "o200k_base"      # gpt-4o / gpt-4.1 / o-series (tiktoken)
TK_CL100K = "cl100k_base"    # gpt-4 / gpt-3.5-turbo (tiktoken)
TK_CLAUDE = "claude"         # Anthropic (proprietary; no public exact tokenizer)
TK_GEMINI = "gemini"         # Google (SentencePiece; not publicly pinned here)
TK_DEEPSEEK = "deepseek"
TK_LLAMA = "llama"
TK_QWEN = "qwen"
TK_MISTRAL = "mistral"
TK_UNKNOWN = "unknown"


# Ordered substring rules (first match wins). Longer/more specific first.
_RULES = [
    ("gpt-4o", TK_O200K), ("gpt-4.1", TK_O200K), ("chatgpt-4o", TK_O200K),
    ("o1", TK_O200K), ("o3", TK_O200K), ("o4", TK_O200K), ("gpt-5", TK_O200K),
    ("gpt-4", TK_CL100K), ("gpt-3.5", TK_CL100K), ("gpt-35", TK_CL100K),
    ("claude", TK_CLAUDE),
    ("gemini", TK_GEMINI),
    ("deepseek", TK_DEEPSEEK),
    ("llama", TK_LLAMA), ("meta-llama", TK_LLAMA),
    ("qwen", TK_QWEN),
    ("mistral", TK_MISTRAL), ("mixtral", TK_MISTRAL),
]

# Families for which we ship (or can build) a reliable public tokenizer reference.
# For everything else, single-endpoint tokenizer classification stays inconclusive
# and we recommend --compare instead.
CALIBRATABLE = {TK_O200K, TK_CL100K}


def tokenizer_family(model: Optional[str]) -> str:
    if not model:
        return TK_UNKNOWN
    m = model.lower()
    for needle, fam in _RULES:
        if needle in m:
            return fam
    return TK_UNKNOWN


def describe(model: Optional[str]) -> Dict[str, str]:
    fam = tokenizer_family(model)
    return {
        "claimed_model": model or "",
        "tokenizer_family": fam,
        "reference_available": "yes" if fam in CALIBRATABLE else "no",
    }
