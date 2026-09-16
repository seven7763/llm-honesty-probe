# Issue backlog (not yet probes)

Candidates captured from live runs. Nothing here is implemented — each entry
needs its own reproduction and design pass before becoming a probe.

## `dimensions` silently ignored by embedding-style gateways

Captured 2026-09-15/16 while testing an OpenAI-compatible gateway
(`text-embedding` family with native width 384): an embedding request that asked
for a reduced dimensionality (`dimensions: 128`) returned HTTP 200 with a
384-wide vector — the parameter was dropped silently, no error, no echo. A
client that trusts `dimensions` gets vectors of the wrong size and a puzzle
that "the endpoint ignored my parameter". (Recorded internally as
"请求 128 返回原生 384 不报错".)

Candidate detection (a "does this endpoint honor what you asked for" probe):
request an embedding with `dimensions=128`, then measure `len(data[0]["embedding"])`.
- 128 → honored;
- native width (observed: 384 where 128 was asked) → silently ignored →
  **inconclusive for honesty** (many gateways pass embeddings through untruncated;
  this is a capability/contract gap, not a downgrade signal — never SUSPICIOUS);
- error → also inconclusive, endpoint rejects the parameter.

Open questions before building: does this belong in the honesty-probe scope at
all (it checks parameter fidelity, not model identity)? Which free/cheap
embedding ids are stable enough to probe? Needs a couple more observations from
different gateways before we commit a verdict rule.
