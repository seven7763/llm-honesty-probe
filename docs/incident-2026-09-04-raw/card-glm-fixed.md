```
+------------------------------------------------------------------------+
| LLM HONESTY PROBE · verdict card                                 v0.2.0|
+------------------------------------------------------------------------+
|                                                                        |
|  ===  PASS  ===                                                        |
|  No downgrade signals in this run.                                     |
|                                                                        |
|  claimed model : glm-5.3-flash                                         |
|  endpoint      : https://••• (hidden — safe to share)                  |
|                                                                        |
|  [-] Tokenizer fingerprint                                             |
|        No verdict — add --compare for a definitive check.              |
|  [+] Capability floor                                                  |
|        Produced exact JSON as requested.                               |
|  [+] Long context                                                      |
|        Recalled the needle at all tested lengths (up to ~8000 chars).  |
|  [+] Consistency                                                       |
|        Identical output on all 3 calls at temp=0.                      |
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

**Verdict: PASS** — No downgrade signals in this run.

| Signal | Result |
|---|---|
| – Tokenizer fingerprint | No verdict — add --compare for a definitive check. |
| ✓ Capability floor | Produced exact JSON as requested. |
| ✓ Long context | Recalled the needle at all tested lengths (up to ~8000 chars). |
| ✓ Consistency | Identical output on all 3 calls at temp=0. |
| – Self-report | Claimed model family unknown; can't compare self-report. |

> These are **heuristic signals, not proof.** Test the endpoint *you* pay for — it's one command, your key never leaves your machine: https://github.com/seven7763/llm-honesty-probe
