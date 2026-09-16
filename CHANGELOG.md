# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.2] - 2026-09-16

### Fixed
- **"Request failed: unknown" on quota refusals.** On a free-tier key (or any
  gateway group without a routable channel for the model), the strict-format and
  refusal tasks previously reported a bare `Request failed: unknown` with empty
  evidence, and the needle probe reported `outcomes: null` with no cause —
  indistinguishable from a context-limit error. The client's error is now
  surfaced in the detail and stored in the evidence.
- **Budget-starved replies mislabelled as request failures.** When a reasoning
  model returned `200 OK` + empty content + `finish_reason=length`, the format
  and refusal signals said "Request failed" (it didn't fail — the thinking ate
  the budget). They now say so explicitly and point at `--max-tokens`, keeping
  the v0.2.1 rule that starvation is never a red flag.

### Added
- **Free-tier-limited diagnosis.** A conservative matcher
  (`client.free_tier_limited()`) recognises quota / rate-limit / model-not-found
  responses by observed shapes: HTTP 429, `insufficient_quota` / `quota`,
  `rate limit`, credit/exhaust wording, and NewAPI-style `model_not_found` /
  `无可用渠道` 503s. When needle or a reasoning request hits such a refusal, the
  signal stays **inconclusive** (never suspicious — "the probe couldn't run" is
  not "the endpoint is dishonest") and carries a `free-tier-limited` tag,
  visible on the verdict card and in the JSON `tags` field.
- `Signal.tags` (dataclass field + JSON output + all four card renderers).
- Mock-server modes `quota`, `no_channel`, `flaky_500` and
  `tests/test_free_tier.py`: the classifier is asserted to match observed
  bodies and to *not* match unrelated 500s / network errors (miss rather than
  mislabel).

## [0.2.1] - 2026-09-04

### Fixed
- **Reasoning-model false positive.** Endpoints that serve reasoning models can
  spend the entire `max_tokens` budget on hidden thinking tokens and return empty
  visible content with `finish_reason: "length"`. The needle, reasoning-floor,
  strict-JSON and identity probes previously read that empty reply as a capability
  failure and flagged `SUSPICIOUS` — on an honest endpoint. Such responses are now
  treated as inconclusive (budget starvation is a property of the caller's
  `max_tokens`, not of the server's honesty), and the default per-call budgets were
  raised so short factual replies still fit.
- **Tokenizer probe vs gateways enforcing `max_tokens > 1`.** The fingerprint
  calls used `max_tokens=1`, which some OpenAI-compatible gateways reject outright
  (HTTP 400 `max_tokens must be greater than 2`), silently degrading the probe to
  inconclusive. The calls now request 4 tokens.

### Added
- `ChatResult.finish_reason` / `ChatResult.reasoning_tokens` (both protocols), and
  `client.budget_starved()` — the shared guard probes use to tell "empty because
  thinking ate the budget" from "empty because the server is evasive".
- Mock-server `reasoning=True` mode + regression tests: a budget-starved reasoning
  response must never raise suspicion on the needle or capability-floor probes.

## [0.2.0] - 2026-07-20

### Added
- **`--card`: a share-friendly verdict card.** Distills a run into a single
  `PASS` / `SUSPICIOUS` (with `REVIEW` / `INCONCLUSIVE` fallbacks) snapshot of the
  four headline signals — tokenizer fingerprint, capability floor, long context,
  and consistency — plus a muted, explicitly-spoofable self-report footnote.
- **Multiple card formats** via `--card-format`: `txt` (default), `md`
  (forum-ready), `svg`, `html` (self-contained, screenshot at 2x), `png`, or `all`.
  PNG export is best-effort (uses `cairosvg` or a CLI rasterizer if present) and
  never becomes a runtime dependency; it falls back to writing an `.svg`.
- **`--card-out`** to write the card to a file or (with `--card-format all`) a
  directory; **`--card-show-endpoint`** to opt into showing the tested host.
- `--self-test --card` renders **two** sample cards (an honest `PASS` and a
  degraded `SUSPICIOUS`) so both states are visible with no key or network.
- Committed sample cards under [`examples/cards/`](examples/cards/).
- `tests/test_card.py` covering verdicts, all render formats, endpoint masking,
  and key-safety across every card format.

### Safety / behavior
- The endpoint host is **masked by default** on cards so a shared card does not
  out the provider you tested. Opt in with `--card-show-endpoint`.
- All card surfaces inherit the existing redaction layer: the API key can never
  appear on a card.
- No changes to the probes, the report output, the client, or key handling. The
  card is a new, additive rendering of the same signals.

## [0.1.0]

- Initial release: heuristic probes (tokenizer fingerprint, capability floor,
  long-context needle recall, consistency, self-report) with text/JSON reports,
  a differential `--compare` mode, a built-in `--self-test` mock, and a
  key-safety layer (env-only key, redaction on every output path).
