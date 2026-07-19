"""llm-honesty-probe: heuristic signals about whether an OpenAI-/Anthropic-compatible
endpoint is serving the model it claims.

This tool produces *signals*, not proof. See the README's "Limitations" section.
It is provider-neutral: point it at anyone, including the gateway its authors work on.
"""

__all__ = ["__version__"]

__version__ = "0.2.0"
