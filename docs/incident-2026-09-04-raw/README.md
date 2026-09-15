# Raw reports — incident 2026-09-04 self-test

These are the original machine-generated reports behind
[`../incident-2026-09-04-self-test.md`](../incident-2026-09-04-self-test.md),
published so the timeline in that document can be checked against the actual
tool output instead of our summary of it.

## Files → timeline

| File | Timeline step | Content |
|---|---|---|
| `probe-glm.json` | Run 1, 08:00–08:01 (v0.2.0) | JSON report: 2 consistent / 3 suspicious / 4 inconclusive — the false-positive `SUSPICIOUS` run |
| `probe-glm2.json` | Run 2, 08:03 (v0.2.0, same config) | JSON report: 4 / 1 / 4 — two of three flags vanish with no code change |
| `probe-glm-fixed.json` | Run 3, 08:16–08:19 (fixed code) | JSON report: 6 / 0 / 3 — the `PASS` re-run |
| `card-glm.md` | Run 1's verdict card | The `SUSPICIOUS` card, as printed (endpoint masked by the tool's own `--card` redaction) |
| `card-glm-fixed.md` | Run 3's verdict card | The `PASS` card, as printed |

The header of `probe-glm-fixed.json` and the PASS card still read `0.2.0`:
Run 3 was captured seconds before the version bump was committed — noted in
the incident document as an artifact of the ordering, not edited here.

## Redaction

Published versions are byte-identical to the archived originals **except**:

- `probe-glm.json` and `probe-glm2.json`: the gateway's `request id` inside
  the tokenizer probe's HTTP 400 error detail was replaced with
  `[redacted]` (2 occurrences total, one per file) — request ids are
  account-correlatable identifiers and add nothing to the record.

Nothing else was removed. In particular:

- **API keys were never in these files**: the runs read the key from an
  environment variable; the report format does not embed credentials.
- **The endpoint host (`jp.daoxe.com`) is deliberately kept** in the JSON
  `meta.base_url` — this is a self-test against a gateway we operate, and the
  point of publishing the raw reports is that the accusation named no one it
  shouldn't. The verdict *cards* mask the endpoint because that is what the
  tool prints for everyone (`--card` hides the host by default); the raw JSON
  keeps it, and we say so here rather than pretending otherwise.

*Signals, not proof — including the record of the time the signals were wrong.*
