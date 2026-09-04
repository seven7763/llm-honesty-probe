"""A tiny, dependency-free HTTP client for OpenAI- and Anthropic-compatible endpoints.

Only the Python standard library is used (``urllib``), so there is nothing to
audit in a lockfile and nothing to install. The key is read from the environment
by the CLI and handed here in memory; it is registered with :mod:`redaction` and
never printed by this module.
"""

from __future__ import annotations

import dataclasses
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from . import redaction

DEFAULT_TIMEOUT = 60.0
_USER_AGENT = "llm-honesty-probe/0.1 (+https://github.com/seven7763/llm-honesty-probe)"


@dataclasses.dataclass
class ChatResult:
    ok: bool
    http_status: int
    latency_ms: float
    text: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model_reported: Optional[str] = None       # the "model" field the server echoed
    system_fingerprint: Optional[str] = None   # OpenAI-only, when present
    logprob_tokens: Optional[List[str]] = None # token *strings*, when logprobs given
    finish_reason: Optional[str] = None        # 'length' + empty text = reasoning budget exhausted
    reasoning_tokens: Optional[int] = None     # hidden thinking tokens, when reported
    error: Optional[str] = None                # already redacted
    raw_keys: Optional[List[str]] = None       # top-level keys of the response, for debugging


@dataclasses.dataclass
class Endpoint:
    base_url: str
    protocol: str = "openai"          # "openai" | "anthropic"
    api_key: Optional[str] = None     # held in memory only; never logged
    timeout: float = DEFAULT_TIMEOUT
    anthropic_version: str = "2023-06-01"
    label: str = "endpoint"

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if self.api_key:
            redaction.register_secret(self.api_key)

    # -- URL helpers ---------------------------------------------------------
    def _url(self, path: str) -> str:
        # Allow callers to pass a base_url that already ends in /v1 or not.
        base = self.base_url
        if base.endswith("/v1") and path.startswith("/v1"):
            path = path[len("/v1"):]
        return base + path

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
        if self.protocol == "anthropic":
            if self.api_key:
                headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = self.anthropic_version
        else:
            if self.api_key:
                headers["Authorization"] = "Bearer " + self.api_key
        return headers

    # -- low-level POST ------------------------------------------------------
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST JSON and return {status, latency_ms, body(dict|None), error(str|None)}."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url(path), data=data,
                                     headers=self._headers(), method="POST")
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                latency = (time.perf_counter() - start) * 1000.0
                body = resp.read().decode("utf-8", "replace")
                status = resp.getcode()
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    return {"status": status, "latency_ms": latency, "body": None,
                            "error": redaction.redact("non-JSON response: " + body[:200])}
                return {"status": status, "latency_ms": latency, "body": parsed, "error": None}
        except urllib.error.HTTPError as exc:
            latency = (time.perf_counter() - start) * 1000.0
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001 - never let error handling raise
                detail = ""
            return {"status": exc.code, "latency_ms": latency, "body": None,
                    "error": redaction.redact("HTTP %s: %s" % (exc.code, detail))}
        except urllib.error.URLError as exc:
            latency = (time.perf_counter() - start) * 1000.0
            return {"status": 0, "latency_ms": latency, "body": None,
                    "error": redaction.redact("network error: %s" % (exc.reason,))}
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000.0
            return {"status": 0, "latency_ms": latency, "body": None,
                    "error": redaction.redact("unexpected error: %s" % (exc,))}

    # -- public: one chat turn ----------------------------------------------
    def chat(self, *, model: str, messages: List[Dict[str, str]],
             temperature: float = 0.0, max_tokens: int = 16,
             logprobs: bool = False, system: Optional[str] = None) -> ChatResult:
        if self.protocol == "anthropic":
            return self._chat_anthropic(model, messages, temperature, max_tokens, system)
        return self._chat_openai(model, messages, temperature, max_tokens, logprobs, system)

    # -- OpenAI Chat Completions --------------------------------------------
    def _chat_openai(self, model, messages, temperature, max_tokens, logprobs, system):
        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs
        payload: Dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = 1
        r = self._post("/v1/chat/completions", payload)
        if r["error"] is not None or not r["body"]:
            return ChatResult(ok=False, http_status=r["status"], latency_ms=r["latency_ms"],
                              error=r["error"] or "empty response")
        body = r["body"]
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        usage = body.get("usage") or {}
        logprob_tokens = _extract_openai_logprob_tokens(choice)
        return ChatResult(
            ok=True, http_status=r["status"], latency_ms=r["latency_ms"],
            text=text if isinstance(text, str) else json.dumps(text),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            model_reported=body.get("model"),
            system_fingerprint=body.get("system_fingerprint"),
            logprob_tokens=logprob_tokens,
            finish_reason=choice.get("finish_reason"),
            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            raw_keys=sorted(body.keys()),
        )

    # -- OpenAI legacy Completions (for echo-based tokenizer fingerprint) -----
    def complete_echo(self, *, model: str, prompt: str) -> ChatResult:
        """Best-effort: use /v1/completions with echo+logprobs to read how the
        server tokenizes the *prompt* itself. Many chat-only gateways 404 here;
        that's fine, the caller treats it as inconclusive."""
        payload = {"model": model, "prompt": prompt, "max_tokens": 0,
                   "echo": True, "logprobs": 0, "temperature": 0}
        r = self._post("/v1/completions", payload)
        if r["error"] is not None or not r["body"]:
            return ChatResult(ok=False, http_status=r["status"], latency_ms=r["latency_ms"],
                              error=r["error"] or "empty response")
        body = r["body"]
        choice = (body.get("choices") or [{}])[0]
        lp = choice.get("logprobs") or {}
        tokens = lp.get("tokens")
        usage = body.get("usage") or {}
        return ChatResult(
            ok=True, http_status=r["status"], latency_ms=r["latency_ms"],
            prompt_tokens=usage.get("prompt_tokens"),
            model_reported=body.get("model"),
            logprob_tokens=tokens if isinstance(tokens, list) else None,
            raw_keys=sorted(body.keys()),
        )

    # -- Anthropic Messages --------------------------------------------------
    def _chat_anthropic(self, model, messages, temperature, max_tokens, system):
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        r = self._post("/v1/messages", payload)
        if r["error"] is not None or not r["body"]:
            return ChatResult(ok=False, http_status=r["status"], latency_ms=r["latency_ms"],
                              error=r["error"] or "empty response")
        body = r["body"]
        text = _extract_anthropic_text(body)
        usage = body.get("usage") or {}
        return ChatResult(
            ok=True, http_status=r["status"], latency_ms=r["latency_ms"], text=text,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            model_reported=body.get("model"),
            finish_reason={"max_tokens": "length", "stop_sequence": "stop"}.get(body.get("stop_reason"), body.get("stop_reason")),
            raw_keys=sorted(body.keys()),
        )


def _extract_openai_logprob_tokens(choice: Dict[str, Any]) -> Optional[List[str]]:
    lp = choice.get("logprobs")
    if not isinstance(lp, dict):
        return None
    content = lp.get("content")
    if isinstance(content, list):
        toks = [c.get("token") for c in content if isinstance(c, dict) and "token" in c]
        return toks or None
    return None


def _extract_anthropic_text(body: Dict[str, Any]) -> str:
    parts = body.get("content")
    if isinstance(parts, list):
        out = []
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
        return "".join(out)
    if isinstance(parts, str):
        return parts
    return ""


def budget_starved(r: "ChatResult") -> bool:
    """True when the endpoint returned OK but produced no visible content
    because the output budget was consumed by hidden reasoning tokens
    (finish_reason == 'length' with empty text). This is a property of the
    caller's max_tokens vs a reasoning model, NOT an honesty signal — probes
    must treat it as inconclusive, never suspicious."""
    return bool(r.ok) and not (r.text or "").strip() and r.finish_reason == "length"
