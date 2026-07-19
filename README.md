# llm-honesty-probe

**A small, provider-neutral CLI that gives you *signals* about whether an
OpenAI- or Anthropic-compatible endpoint is actually serving the model it
claims — or quietly downgrading you.**

> **Read this first — what this tool is and is not.**
> It produces **heuristic signals, not cryptographic proof.** You cannot prove
> from the outside which weights a provider runs. What you *can* do is collect
> repeatable behavioral evidence that catches the common cheats (model
> substitution, heavy quantization, context truncation, silent fallback). Treat
> a clean run as *reassuring*, not a guarantee; treat a flag as a *reason to look
> closer*, not a conviction. The [Limitations](#limitations) section is not
> boilerplate — please read it.

- **Zero runtime dependencies.** Pure Python standard library. Nothing to
  `pip install`, nothing in a lockfile to audit. Clone it and read it.
- **Your API key is never printed, logged, or stored.** It is read *only* from an
  environment variable (there is deliberately no `--key` flag), and every line of
  output passes through a redaction layer. See [Key safety](#key-safety).
- **Provider-neutral on purpose.** Point it at anyone — a relay you're evaluating,
  the official API, a local model server, or the gateway the authors work on
  (see [Disclosure](#disclosure)). The tool doesn't care who you test.

---

## Why this exists

Cheap "GPT / Claude / DeepSeek" API relays have a trust problem nobody advertises:
some quietly swap in a smaller, quantized, or context-truncated model. The nasty
part is the *timing* — it often works fine on day one and degrades weeks later,
right after you've stopped checking. And the obvious check doesn't work:

> **Asking the model "what model are you?" is useless.** That answer comes from a
> system prompt or fine-tune and is trivially spoofed. You have to test
> **capability and behavior**, not self-report.

So this tool automates a fixed battery of behavioral probes, pins the parameters,
measures instead of eyeballing, and (optionally) diffs your endpoint against a
reference you trust.

---

## Install

No dependencies, so the most trustworthy path is to just clone and run:

```bash
git clone https://github.com/seven7763/llm-honesty-probe
cd llm-honesty-probe
python3 -m llm_honesty_probe --self-test        # runs against a built-in mock; no key needed
```

Requires Python 3.8+. After the package is published you'll also be able to run it
without cloning (e.g. `pipx run llm-honesty-probe ...`), but cloning keeps the
"read the code before you run it" property that an honesty tool should have.

---

## Quickstart

The key is read from an environment variable — never passed on the command line:

```bash
export OPENAI_API_KEY="sk-...your key..."        # never appears in argv or history

# 1) Single endpoint: does this endpoint behave like the model it claims?
python3 -m llm_honesty_probe \
  --base-url https://any-provider.example/v1 \
  --claimed-model gpt-4o

# 2) Differential (strongest): diff the relay against the official API.
export OPENAI_API_KEY_OFFICIAL="sk-...official key..."
python3 -m llm_honesty_probe \
  --base-url https://cheap-relay.example/v1 --claimed-model gpt-4o \
  --compare-base-url https://api.openai.com/v1 --compare-model gpt-4o \
  --compare-api-key-env OPENAI_API_KEY_OFFICIAL

# 3) Claude Code / Anthropic-shaped endpoints:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 -m llm_honesty_probe \
  --base-url https://any-provider.example --protocol anthropic \
  --claimed-model claude-sonnet-4

# JSON for CI / cron; pick specific probes; list what's available:
python3 -m llm_honesty_probe --self-test --json
python3 -m llm_honesty_probe --list-probes
```

### Example output (from `--self-test`, i.e. a deliberately downgraded mock)

```
llm-honesty-probe v0.1.0  —  heuristic signals, NOT proof
Endpoint : http://127.0.0.1:0/v1 (openai)   claimed model: gpt-4o
Mode     : self-test (mock endpoint)
Probes   : consistency, identity, needle, reasoning, tokenizer
------------------------------------------------------------------
[!!] identity    Self-reported identity             (low)
     Claimed gpt but self-reports llama. Weak signal (spoofable both ways).
[!!] needle      Long-context recall                (low)
     Recall broke at ~8000 chars. Could be silent truncation or the model's real limit; diff to disambiguate.
[!!] reasoning   Capability floor (reasoning)       (medium)
     Failed 4/4 easy reasoning tasks a full-tier model rarely misses.
------------------------------------------------------------------
Summary: 2 consistent · 4 suspicious · 3 inconclusive
Some signals warrant a closer look (diff against the official endpoint).
Reminder: these are heuristic signals, not cryptographic proof. [...] See LIMITATIONS.
```

`[OK]` = consistent · `[!!]` = suspicious · `[--]` = inconclusive. Each signal
carries a **confidence** (low / medium / high) because not all signals are equal.

---

## Methodology

Every probe is designed to (a) test behavior rather than self-report, (b) degrade
to *inconclusive* when a feature is unsupported or noisy, and (c) never decide a
provider is lying from a single weak signal.

### 1. Tokenizer fingerprint (`tokenizer`)
Different model families use different tokenizers, and the tokenizer leaks through
the `usage.prompt_tokens` the server reports. We send a battery of crafted strings
(digit runs, whitespace, CJK, emoji, code, URLs, mixed unicode) and record how
many tokens each costs.

To cancel the fixed per-request chat-template overhead, we measure a **delta**:
`tokens(anchor + probe) − tokens(anchor)`. The resulting vector is close to the
raw token count of each string and is comparable across requests.

- **With `--compare` (best, reference-free):** diff the vector against a reference
  endpoint serving the same model id. A different vector means a different
  tokenizer, which means a different model/family — a *high-confidence* signal.
- **Single endpoint:** classify the vector against a shipped reference table of
  known tokenizers (OpenAI's `cl100k_base` / `o200k_base`, generated from
  `tiktoken` — see [`scripts/build_reference.py`](scripts/build_reference.py), so
  the numbers are reproducible, not hand-written). If the claimed family has no
  public reference (Claude, Gemini, …), the probe says *inconclusive, use
  `--compare`* rather than guessing.

### 2. Capability floor (`reasoning`)
A handful of tasks with **objectively checkable answers the tool already knows**
(multi-step arithmetic, string reversal, character counting) plus a **strict-JSON**
format test and a **refusal-behavior** check on a clearly benign prompt. These are
trivial for any full-tier model; a downgraded or heavily quantized substitute is
more likely to trip. We weight *failure* more than success — passing an easy task
proves little, but a "flagship" that fails a floor task is worth surfacing.

### 3. Long-context recall (`needle`)
We generate deterministic filler text, hide a unique passphrase in the middle, and
ask the endpoint to read it back — across several context lengths. Because **the
tool places the needle, it always knows the right answer** (no external key
needed). Recall that works at short context but breaks at longer context is the
classic signature of **silent context truncation** (a relay capping your window to
save tokens).

### 4. Stability & performance (`consistency`)
Repeats one fixed prompt N times at `temperature=0` and looks at output
determinism, the stability of the server-reported `model` field and OpenAI
`system_fingerprint`, plus **p50/p95 latency and error rate** (informational). A
server that reports different `model` values or wildly different outputs for
identical calls may be routing you across different backends.

### 5. Self-report (`identity`) — deliberately low weight
Asks the model to name itself and compares to the claim. This is included *because
its absence would be conspicuous*, but it is trivially spoofable in both
directions, so its confidence is capped at **low** and it never drives a verdict on
its own.

### Design principles
- **temperature=0**, fixed `max_tokens`, fixed system prompt — remove randomness.
- **Measure, don't eyeball** — one call tells you nothing.
- **Diff against a reference** you trust whenever you can (`--compare`).
- **Re-run on a schedule** — silent degradation is a time-series problem, not a
  launch-day one. The JSON output is meant to be diffed in cron/CI over time.

---

## Limitations

Please take these as seriously as the features. Overstating an honesty tool
defeats its purpose.

- **These are signals, not proof.** None of this cryptographically establishes
  which weights a provider runs. A determined provider that mirrors the official
  tokenizer *and* matches capability *and* holds long context *and* stays stable
  is, for practical purposes, giving you the model — but this tool cannot prove
  intent or rule out sophisticated spoofing.
- **The probe set is small and opinionated.** A provider that knows these exact
  probes could special-case them. That's why the strongest mode is a *differential
  diff* you control, and why PRs that make the probes harder to fake are welcome.
- **Token accounting varies.** Some providers don't return `usage`, estimate it,
  or bill with quirks; a junction merge can shift a delta by a token. The
  tokenizer probe uses a tolerance and falls back to *inconclusive* rather than
  accuse.
- **`temperature=0` is not guaranteed deterministic** on real hardware, so the
  determinism signal is intentionally low confidence.
- **Legitimate reasons for "suspicious".** A smaller model can be the *correct*
  answer if that's what you asked for; a short context limit can be the model's
  real limit, not truncation; different infrastructure can change latency. Use
  `--compare` to disambiguate.
- **Refusal behavior is noisy.** Alignment differs across honest providers, so the
  refusal check is low confidence by design.
- **This tests an endpoint's *behavior over a moment*, not its contract.** Re-run
  over time; a single run is a snapshot.

---

## Key safety

If you audit one thing, audit [`llm_honesty_probe/redaction.py`](llm_honesty_probe/redaction.py)
and the `Endpoint` header code in [`client.py`](llm_honesty_probe/client.py).

- The key is read **only** from an environment variable named by `--api-key-env`
  (default `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` for `--protocol anthropic`).
  There is no `--key` flag, so your key cannot land in shell history, `ps`/argv, or
  a saved command.
- There is **no code path that prints `api_key` or an `Authorization` header.**
- Everything that could reach your screen, a file, or an error message runs through
  `redact()`, which scrubs both the exact secret and anything matching a common
  key/authorization shape.
- The tool makes only the API calls needed for the selected probes. It writes
  nothing to disk unless you pass `--out`.

---

## Configuration

```bash
--probes tokenizer,reasoning      # subset instead of all
--repeats 10                      # samples for the consistency probe
--needle-lengths 2000,8000,32000  # approx context sizes (chars) to test recall
--reference path/to/tokenizers.json
--config path/to/config.json      # e.g. {"degrade": true} for --self-test
--json --out report.json          # machine-readable, good for cron diffs
```

To (re)generate the tokenizer reference yourself (recommended — don't trust
numbers you didn't compute):

```bash
pip install tiktoken            # dev-only; not a runtime dependency
python scripts/build_reference.py
```

---

## Neutrality

This tool is not tied to any provider. It ships no provider allow-list, no
"preferred" endpoint, and no telemetry. The comparison workflow treats the
official API and any relay identically. That neutrality is the point: a
verification tool is only useful if it will just as happily flag the people who
wrote it.

## Disclosure

This project was started by people who work on **daoxe**, an OpenAI-compatible
LLM gateway (it also speaks Anthropic Messages natively for Claude Code). We built
it because we'd rather you *verify* a provider than take a vendor's word for it —
including ours. Point it at daoxe and at whatever you use today, and compare:
[daoxe.com](https://daoxe.com/?utm_source=github&utm_medium=organic&utm_campaign=en_launch).
daoxe actively encourages users to run this against its endpoints; if it ever
fails these checks, that's a bug report we want.

The tool's usefulness does not depend on daoxe, and nothing here privileges it.

## Related

Two sibling projects, if you're evaluating an endpoint end to end:

- **[llm-gateway-benchmark](https://github.com/seven7763/llm-gateway-benchmark)** — a
  reproducible *speed & availability* benchmark (success rate, p50/p95 latency,
  $/1M tokens). It answers "is this endpoint fast and cheap?"; this tool answers
  "is it actually the model it claims?" The two are complementary, not competing.
- **[DaoXE-AI](https://github.com/seven7763/DaoXE-AI)** — OpenAI-/Anthropic-compatible
  gateway setup examples for Cursor, Claude Code & Cline (same authors — see
  [Disclosure](#disclosure)). Point this probe at it and compare it against
  whatever you use today.

## Contributing

The best contributions are **harder-to-fake probes** and **additional tokenizer
references**. If you can think of a behavioral check a downgraded relay can't
cheaply spoof, please open a PR or issue.

## License

MIT — see [LICENSE](LICENSE).
