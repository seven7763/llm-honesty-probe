# Incident 2026-09-04: a false positive against our own gateway

**TL;DR** — The one time this tool has been publicly wrong was against
ourselves. On
2026-09-04 we ran v0.2.0 against one of the groups on the gateway the authors
operate. It returned `SUSPICIOUS` — wrongly. The endpoint did nothing
dishonest; the needle and reasoning probes misread an *empty reply* as a
*capability failure*.
Fixed in v0.2.1 ([`cb15e61`](https://github.com/seven7763/llm-honesty-probe/commit/cb15e61)),
re-ran, `PASS` — with the known inconclusive signals still standing, as they
should. This document is the full record, published because a tool that
cannot show the one time it was wrong is a tool you cannot calibrate.

---

## Timeline (2026-09-04, UTC+8)

| Time | Event |
|---|---|
| 08:00–08:01 | **Run 1** (v0.2.0): verdict card says **SUSPICIOUS** — 2 consistent / 3 suspicious / 4 inconclusive. |
| 08:03 | **Run 2**, same configuration two minutes later: 4 / 1 / 4 — two of the three flags vanish with no code change. The instability is itself a clue. |
| 08:03–08:12 | Diagnosis against the source: grepping every `max_tokens` in the probes, reading the raw responses, finding the HTTP 400 the tokenizer probe had swallowed. |
| 08:09–08:12 | Fix drafted: budget-starvation guard + probe budget raise + tokenizer `max_tokens` 1 → 4 + mock-server `reasoning` mode + regression tests. |
| 08:16–08:19 | **Run 3** (fixed code): verdict card says **PASS** — 6 consistent / 0 suspicious / 3 inconclusive. |
| 08:20 | [`cb15e61`](https://github.com/seven7763/llm-honesty-probe/commit/cb15e61) ships as v0.2.1. 20/20 tests pass, including two new regressions that replay exactly this failure shape against a mock. |

*(A small artifact of the ordering: Run 3 was captured seconds before the
version bump was committed, so the JSON header and card of the PASS run still
read `0.2.0` even though they ran the fixed code.)*

## What the false positive looked like

Key sections, verbatim from Run 1's JSON report (endpoint host masked, as the
card would mask it; the `identity` probe's reply was also `""`):

```json
{"probe": "needle", "title": "Long-context recall",
 "verdict": "suspicious", "confidence": "low",
 "detail": "Recall broke at ~8000 chars. Could be silent truncation or the model's real context limit; diff against the official endpoint to disambiguate.",
 "evidence": {"outcomes": {"8000": false}, "lengths_chars": [8000]}}

{"probe": "reasoning", "title": "Capability floor (reasoning)",
 "verdict": "suspicious", "confidence": "medium",
 "detail": "Failed 2/4 easy reasoning tasks a full-tier model rarely misses.",
 "evidence": {"results": {
   "arithmetic": {"ok": true,  "reply": "396"},
   "reverse":    {"ok": false, "reply": ""},
   "count":      {"ok": false, "reply": ""},
   "multistep":  {"ok": true,  "reply": "58"}}}}

{"probe": "reasoning", "title": "Strict format following",
 "verdict": "suspicious", "confidence": "low",
 "detail": "Did not return valid JSON when strictly instructed to.",
 "evidence": {"reply": "{\"a\":"}}

{"probe": "tokenizer", "title": "Tokenizer fingerprint",
 "verdict": "inconclusive", "confidence": "low",
 "detail": "Can't fingerprint tokenizer: HTTP 400: {\"error\":{\"message\":\"max_tokens must be greater than 2 …\",\"type\":\"invalid_request\", …}}"}
```

A `SUSPICIOUS` on a route we operate ourselves — printed with the same voice
the tool uses for everyone else.

## Three clues that located it

1. **The failures were empty, not wrong.** `reverse` and `count` returned
   `""`, while `arithmetic` and `multistep` returned *correct* short answers
   (`396`, `58`). A substituted or quantized model fails with wrong content;
   empty content on some tasks and correct content on the shortest ones is
   the shape of an output budget running out mid-generation. Run 1's strict-JSON
   reply `{"a":` — the opening of the object, then nothing — makes it
   explicit: generation hit the cap.
2. **The same traffic didn't agree with itself.** Two consecutive runs,
   identical configuration, two minutes apart: 3 suspicious → 1 suspicious.
   The capability-floor flag downgraded from a medium-confidence "failed 2/4"
   to "failed 1/4, could be formatting" once the model produced real — if
   garbled (`ytenoh`) — replies instead of empty ones. Server honesty does not
   flicker on a two-minute scale; a budget race does. (Run 2 even showed the
   *inverse* artifact: its determinism check reported "consistent, identical
   output on all 3 calls" when the identical output was three empty strings —
   vacuously green.)
3. **The tokenizer probe said the mechanism out loud.** Its report carried a
   raw gateway error: `HTTP 400 … max_tokens must be greater than 2`. The
   probe had been asking for `max_tokens=1` to isolate prompt-token counts,
   a shape this gateway refuses. The probe degraded to inconclusive silently
   instead of surfacing that its own parameters were rejected.

## Root cause

Reasoning-capable upstreams spend completion tokens on hidden thinking
*before* answering. When `max_tokens` is small, the entire budget goes to
reasoning and the visible reply is `content: ""` with
`finish_reason: "length"` (and a `usage.completion_tokens_details.reasoning_tokens`
count of where the tokens went). v0.2.0 parsed none of that: `ChatResult`
had no `finish_reason` or `reasoning_tokens` field at all, so every probe
saw "empty reply" and some read it as "failed", "evasive", or "suspicious".
The needle, capability-floor, strict-JSON and identity probes hard-coded
per-call budgets of 32/64/120 tokens — trivially small next to a thinking
model's preamble. Budget starvation is a property of the caller's
`max_tokens`, not of the server's honesty. The tool was accusing itself of
its own parameter choice.

## The fix (v0.2.1, `cb15e61`, 2026-09-04)

- `ChatResult` gained `finish_reason` and `reasoning_tokens` (parsed for both
  the OpenAI and Anthropic shapes), and `client.budget_starved()` — the
  shared guard: response OK, visible text empty, `finish_reason == "length"`.
- The needle and reasoning probes (capability floor, strict-JSON) now route
  that shape to **inconclusive** via the shared `budget_starved()` guard,
  instead of suspicion, and the hard-coded per-call budgets went 32/64/120 → 256
  (identity included); the consistency probe raised its cap the same way
  (16 → 256), since an all-empty determinism sample is the vacuous-green case
  shown above.
- The tokenizer probe's measurement calls went `max_tokens=1` → `4`, so
  gateways that enforce `max_tokens > 2` answer instead of 400-ing.
- The mock server gained a `reasoning=True` mode that replays this exact
  failure shape (empty content, `finish_reason: "length"`, all budget
  consumed as reasoning tokens), plus two regression tests asserting the
  needle and capability-floor probes must **never** return SUSPICIOUS under
  it. Full suite: 20/20.

## The re-run

Run 3 against the same route, fixed code: **PASS** — 6 consistent /
0 suspicious / 3 inconclusive. Needle recalled at 2k and 8k chars; the four
floor tasks all passed; strict JSON produced exactly; three identical
non-empty replies at `temp=0`.

The two substantive inconclusives **remain inconclusive**, and the card says
so — this is not a pass on everything:

- **Tokenizer fingerprint**: single-endpoint mode has no reference to diff
  against, so the structural match (`o200k_base`, distance 90) is reported
  without a verdict; a definitive read needs `--compare` against the official
  endpoint.
- **Self-report**: the claimed model's family is unknown to the built-in
  table, so the identity comparison can't grade itself; it is spoofable and
  low-weight anyway.
- (The third inconclusive is the latency/error-rate line, which is
  informational by design: p50 ≈ 2.2 s, 0% errors over 3 calls.)

Scope, stated plainly: this self-test covers **one group on one gateway** at
one moment. It says nothing about the other routes we operate, and a PASS is
a snapshot, not a guarantee — the same limits the [README
Limitations](../README.md#limitations) section lists for everyone else.

## Why this is published

A false positive is the worst failure mode an honesty-checking tool can have.
It is not "one fewer convincing card"; it is a public accusation against an
endpoint that did nothing wrong, and accusations are harder to retract than
they are to print. The only answer to that risk is to show the machine being
wrong in the open, on traffic where we are the ones with the most to lose —
diagnosed, fixed with regression tests that replay the exact shape, and
re-run without quietly deleting the original reports.

We operate [daoxe](https://daoxe.com), one of the gateways this tool can
point at. We would rather our own verdict cards arrive *with* this incident
attached than arrive spotless. *Signals, not proof* — including ours,
including this one.

---

*References: CHANGELOG `[0.2.1] - 2026-09-04` (this repo), commit `cb15e61`,
tests in `tests/test_probes.py` (`ReasoningBudgetFalsePositiveTest`), mock
mode in `llm_honesty_probe/_mockserver.py`. Full raw reports and verdict cards
from all three runs: [`incident-2026-09-04-raw/`](./incident-2026-09-04-raw/)
(with the redactions listed there).*
