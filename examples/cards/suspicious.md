```
+------------------------------------------------------------------------+
| LLM HONESTY PROBE · verdict card                                 v0.2.0|
+------------------------------------------------------------------------+
|                                                                        |
|  ===  SUSPICIOUS  ===                                                  |
|  Hard to explain if the claim were true.                               |
|                                                                        |
|  claimed model : gpt-4o                                                |
|  endpoint      : built-in self-test mock                               |
|                                                                        |
|  [-] Tokenizer fingerprint                                             |
|        No verdict — add --compare for a definitive check.              |
|  [!] Capability floor                                                  |
|        Failed 4/4 easy reasoning tasks a full-tier model rarely misses.|
|        (medium)                                                        |
|  [!] Long context                                                      |
|        Lost a needle in long context (possible truncation). (low)      |
|  [+] Consistency                                                       |
|        Stable model field / fingerprint across calls.                  |
|  [!] Self-report (spoofable, low weight)                               |
|        Claimed gpt but self-reports llama (low)                        |
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
| ✗ Capability floor | Failed 4/4 easy reasoning tasks a full-tier model rarely misses. (medium) |
| ✗ Long context | Lost a needle in long context (possible truncation). (low) |
| ✓ Consistency | Stable model field / fingerprint across calls. |
| ✗ Self-report | Claimed gpt but self-reports llama (low) |

> These are **heuristic signals, not proof.** Test the endpoint *you* pay for — it's one command, your key never leaves your machine: https://github.com/seven7763/llm-honesty-probe
