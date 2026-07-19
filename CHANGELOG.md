# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

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
