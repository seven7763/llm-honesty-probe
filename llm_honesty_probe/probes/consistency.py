"""Stability across repeated identical calls.

Repeats one fixed prompt N times at temperature=0 and looks at:
  * output determinism (wildly varying answers at temp=0 can indicate the request
    is being load-balanced across different backends/models);
  * stability of the server-reported ``model`` field and OpenAI ``system_fingerprint``;
  * latency p50/p95 and error rate (informational — not an honesty verdict).

temperature=0 is not a hard determinism guarantee, so the determinism signal is
deliberately low confidence.
"""

from __future__ import annotations

from typing import List

from ..client import Endpoint
from ..signals import Signal, CONSISTENT, SUSPICIOUS, INCONCLUSIVE, LOW, MEDIUM, inconclusive
from . import register, ProbeContext

_PROMPT = "In exactly one lowercase word, what is the opposite of 'up'? Reply with only the word."


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = pct / 100.0 * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


@register("consistency", "Repeat one call N times: determinism, backend-identity stability, latency, error rate.")
def run(endpoint: Endpoint, ctx: ProbeContext) -> List[Signal]:
    n = max(2, ctx.repeats)
    outputs = []
    fingerprints = set()
    models = set()
    latencies = []
    errors = 0

    for _ in range(n):
        r = endpoint.chat(model=ctx.claimed_model,
                          messages=[{"role": "user", "content": _PROMPT}],
                          temperature=0.0, max_tokens=16)
        latencies.append(r.latency_ms)
        if not r.ok:
            errors += 1
            continue
        outputs.append((r.text or "").strip().lower())
        if r.system_fingerprint:
            fingerprints.add(r.system_fingerprint)
        if r.model_reported:
            models.add(r.model_reported)

    signals: List[Signal] = []

    # Latency + error rate (informational). ----------------------------------
    err_rate = errors / float(n)
    perf_ev = {
        "n": n, "errors": errors, "error_rate": round(err_rate, 3),
        "p50_ms": round(_percentile(latencies, 50), 1),
        "p95_ms": round(_percentile(latencies, 95), 1),
    }
    signals.append(Signal("consistency", "Latency & error rate (informational)",
                          INCONCLUSIVE, LOW,
                          "p50=%.0fms p95=%.0fms error_rate=%.0f%% over %d calls." %
                          (perf_ev["p50_ms"], perf_ev["p95_ms"], err_rate * 100, n),
                          perf_ev))

    if not outputs:
        signals.append(inconclusive("consistency", "Determinism",
                                    "No successful responses to compare."))
        return signals

    # Determinism. -----------------------------------------------------------
    distinct = sorted(set(outputs))
    det_ev = {"distinct_outputs": distinct[:5], "distinct_count": len(distinct),
              "successful": len(outputs)}
    if len(distinct) == 1:
        signals.append(Signal("consistency", "Determinism", CONSISTENT, LOW,
                              "Identical output on all %d calls at temp=0." % len(outputs), det_ev))
    elif len(distinct) <= max(2, len(outputs) // 3):
        signals.append(Signal("consistency", "Determinism", INCONCLUSIVE, LOW,
                              "%d distinct outputs at temp=0 (mild; temp=0 isn't guaranteed "
                              "deterministic)." % len(distinct), det_ev))
    else:
        signals.append(Signal("consistency", "Determinism", SUSPICIOUS, LOW,
                              "%d distinct outputs for the same temp=0 prompt; possible routing "
                              "across different backends." % len(distinct), det_ev))

    # Backend identity stability. --------------------------------------------
    id_ev = {"model_fields": sorted(models), "system_fingerprints": sorted(fingerprints)}
    if len(models) > 1:
        signals.append(Signal("consistency", "Backend identity", SUSPICIOUS, MEDIUM,
                              "Server reported >1 distinct 'model' value for identical calls: %s."
                              % ", ".join(sorted(models)), id_ev))
    elif len(fingerprints) > 1:
        signals.append(Signal("consistency", "Backend identity", SUSPICIOUS, LOW,
                              "system_fingerprint changed across identical calls (%d distinct)."
                              % len(fingerprints), id_ev))
    else:
        signals.append(Signal("consistency", "Backend identity", CONSISTENT, LOW,
                              "Stable model field / fingerprint across calls.", id_ev))

    return signals
