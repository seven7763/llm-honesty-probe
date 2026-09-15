```
+------------------------------------------------------------------------+
| LLM HONESTY PROBE · verdict card                                 v0.2.0|
+------------------------------------------------------------------------+
|                                                                        |
|  ===  SUSPICIOUS  ===                                                  |
|  Hard to explain if the claim were true.                               |
|                                                                        |
|  claimed model : glm-5.3-flash                                         |
|  endpoint      : https://••• (hidden — safe to share)                  |
|                                                                        |
|  [-] Tokenizer fingerprint                                             |
|        No verdict — add --compare for a definitive check.              |
|  [!] Capability floor                                                  |
|        Failed 2/4 easy reasoning tasks a full-tier model rarely misses.|
|        (medium)                                                        |
|  [!] Long context                                                      |
|        Lost a needle in long context (possible truncation). (medium)   |
|  [+] Consistency                                                       |
|        Stable model field / fingerprint across calls.                  |
|  [-] Self-report (spoofable, low weight)                               |
|        Claimed model family unknown; can't compare self-report.        |
|                                                                        |
|  -> Test the endpoint YOU pay for:                                     |
|     python3 -m llm_honesty_probe \                                     |
|       --base-url <your-endpoint> --claimed-model <model> --card        |
|                                                                        |
+------------------------------------------------------------------------+
|  llm-honesty-probe · open-source · signals, not proof                  |
|  Built by the team behind daoxe — verify us too: daoxe.com             |
+------------------------------------------------------------------------+
```

**Verdict: SUSPICIOUS** — Hard to explain if the claim were true.

| Signal | Result |
|---|---|
| – Tokenizer fingerprint | No verdict — add --compare for a definitive check. |
| ✗ Capability floor | Failed 2/4 easy reasoning tasks a full-tier model rarely misses. (medium) |
| ✗ Long context | Lost a needle in long context (possible truncation). (medium) |
| ✓ Consistency | Stable model field / fingerprint across calls. |
| – Self-report | Claimed model family unknown; can't compare self-report. |

> These are **heuristic signals, not proof.** Test the endpoint *you* pay for — it's one command, your key never leaves your machine: https://github.com/seven7763/llm-honesty-probe
