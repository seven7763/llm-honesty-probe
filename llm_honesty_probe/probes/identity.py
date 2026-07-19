"""Self-report probe (deliberately low weight).

Asking a model "what model are you?" is *not* a reliable check: the answer comes
from a system prompt or fine-tune and is trivially spoofed by a relay. We run it
anyway because a mismatch is still a (weak) signal and the *absence* of the check
would be conspicuous. Confidence is capped at LOW by design.
"""

from __future__ import annotations

from typing import List

from ..client import Endpoint
from ..signals import Signal, CONSISTENT, SUSPICIOUS, LOW, inconclusive
from . import register, ProbeContext

_FAMILY_WORDS = {
    "gpt": ["gpt", "openai", "chatgpt"],
    "claude": ["claude", "anthropic"],
    "gemini": ["gemini", "google", "bard"],
    "deepseek": ["deepseek"],
    "llama": ["llama", "meta"],
    "qwen": ["qwen", "tongyi", "alibaba"],
    "mistral": ["mistral", "mixtral"],
}


def _claimed_family_words(model: str):
    m = (model or "").lower()
    for fam, words in _FAMILY_WORDS.items():
        if any(w in m for w in words):
            return fam, words
    return None, []


@register("identity", "Ask the model to name itself; compare to the claim (spoofable, low weight).")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    prompt = ("What is the exact name and version of the AI model answering this "
              "message? Reply with only the model name, nothing else.")
    res = endpoint.chat(model=ctx.claimed_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0, max_tokens=32)
    if not res.ok:
        return [inconclusive("identity", "Self-reported identity",
                             "Request failed: %s" % (res.error or "unknown"),
                             {"http_status": res.http_status})]

    reply = (res.text or "").strip()
    claimed_fam, _ = _claimed_family_words(ctx.claimed_model)
    reply_l = reply.lower()

    evidence = {"reply": reply[:200], "claimed_model": ctx.claimed_model,
                "model_field": res.model_reported}

    if not claimed_fam:
        return [inconclusive("identity", "Self-reported identity",
                             "Claimed model family unknown; can't compare self-report.",
                             evidence)]

    said_families = [fam for fam, words in _FAMILY_WORDS.items()
                     if any(w in reply_l for w in words)]

    if not said_families:
        return [inconclusive("identity", "Self-reported identity",
                             "Model didn't clearly name a family (reply: %r)." % reply[:60],
                             evidence)]

    if claimed_fam in said_families:
        return [Signal("identity", "Self-reported identity", CONSISTENT, LOW,
                       "Self-report mentions the claimed family (%s). Note: easily spoofed."
                       % claimed_fam, evidence)]

    return [Signal("identity", "Self-reported identity", SUSPICIOUS, LOW,
                   "Claimed %s but self-reports %s. Weak signal (spoofable both ways)."
                   % (claimed_fam, "/".join(said_families)), evidence)]
