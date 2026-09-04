"""A tiny in-process OpenAI-compatible mock endpoint.

Used by ``--self-test`` and the test suite so the whole tool can be exercised
end to end without any real credentials or network access. It is intentionally
"honest" (answers correctly, recalls the needle, is deterministic) so a self-test
shows what a clean run looks like. Pass ``degrade=True`` to simulate a downgraded
relay (wrong answers, context truncation, unstable identity).
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_PASSPHRASE = "SWORDFISH-7492-ALPHA"


def _answer(content: str, degrade: bool, counter: list) -> str:
    c = content.lower()
    if "exact name and version" in c:
        # A degraded relay might leak a different identity intermittently.
        if degrade and counter and counter[0] % 2 == 0:
            return "llama-3-8b"
        return "gpt-4o"
    if "opposite of 'up'" in c:
        return "sideways" if (degrade and counter and counter[0] % 2 == 0) else "down"
    if "((17*23) + (144/12)) - 7" in content:
        return "42" if degrade else "396"
    if "reverse the string 'honesty'" in c:
        return "honesty" if degrade else "ytsenoh"
    if "letter 'a' appear" in c:
        return "4" if degrade else "6"
    if "shelf has 3 boxes" in c:
        return "60" if degrade else "58"
    if "compact json" in c:
        return "here you go: {a: 42}" if degrade else '{"a": 42, "b": "ok"}'
    if "buffer overflow" in c:
        return ("A buffer overflow happens when a program writes past the end of a "
                "buffer, corrupting adjacent memory. It can crash the program or be "
                "exploited to run attacker-controlled code.")
    if "secret passphrase" in c and "reply with only" in c:
        # Honest server recalls; degraded server "truncates" long contexts.
        if degrade and len(content) > 6000:
            return "I couldn't find a passphrase."
        return _PASSPHRASE
    return "ok"


def _approx_tokens(text: str, char_per_token: int = 4) -> int:
    return max(1, len(text) // char_per_token)


class _Handler(BaseHTTPRequestHandler):
    degrade = False
    char_per_token = 4
    reasoning = False   # emulate a reasoning model that spends the whole budget on hidden thinking
    counter = [0]

    def log_message(self, *args):  # silence
        return

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        self.__class__.counter[0] += 1
        model = payload.get("model", "unknown")

        if self.path.endswith("/chat/completions"):
            messages = payload.get("messages", [])
            user = ""
            for m in messages:
                if m.get("role") == "user":
                    user = m.get("content", "")
            ans = _answer(user, self.degrade, self.counter)
            if self.reasoning:
                # visible content empty, finish_reason=length, all budget -> reasoning
                pt = sum(_approx_tokens(m.get("content", ""), self.char_per_token) for m in messages)
                mt = payload.get("max_tokens", 0) or 0
                rresp = {
                    "id": "chatcmpl-mock", "object": "chat.completion", "model": model,
                    "system_fingerprint": "fp_mock_001",
                    "choices": [{"index": 0, "finish_reason": "length",
                                 "message": {"role": "assistant", "content": ""}}],
                    "usage": {"prompt_tokens": pt, "completion_tokens": mt,
                              "total_tokens": pt + mt,
                              "completion_tokens_details": {"reasoning_tokens": mt}},
                }
                return self._send(200, rresp)
            prompt_tokens = sum(_approx_tokens(m.get("content", ""), self.char_per_token)
                                for m in messages)
            resp = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": model,
                "system_fingerprint": "fp_mock_%s" % ("var" if self.degrade else "001"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": ans}}],
                "usage": {"prompt_tokens": prompt_tokens,
                          "completion_tokens": _approx_tokens(ans),
                          "total_tokens": prompt_tokens + _approx_tokens(ans)},
            }
            return self._send(200, resp)

        if self.path.endswith("/completions"):
            return self._send(404, {"error": "legacy completions not supported by mock"})

        return self._send(404, {"error": "not found"})


@contextmanager
def running_server(degrade: bool = False, char_per_token: int = 4, reasoning: bool = False):
    """Context manager yielding a base_url like 'http://127.0.0.1:PORT/v1'."""
    handler = type("H", (_Handler,), {"degrade": degrade,
                                      "char_per_token": char_per_token,
                                      "reasoning": reasoning, "counter": [0]})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield "http://127.0.0.1:%d/v1" % port
    finally:
        server.shutdown()
        server.server_close()
