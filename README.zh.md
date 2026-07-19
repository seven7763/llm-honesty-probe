# llm-honesty-probe（中文说明）

**一个中立、零依赖的命令行工具，用来获取"某个 OpenAI/Anthropic 兼容端点是否在提供它所声称的模型、是否被悄悄降智"的*信号*。**

> **先读这一段——它是什么、不是什么。**
> 本工具输出的是**启发式信号，不是铁证。** 从外部无法密码学地证明一个供应商到底跑的是哪套权重。
> 你能做的，是收集可复现的行为证据，抓住常见的"作弊"：掉包、重度量化、上下文截断、静默降级回退。
> 干净的结果 = *让人安心*，不等于保证；出现红旗 = *值得进一步核查*，不等于定罪。请务必读[局限](#局限)一节。

- **零运行时依赖**：纯 Python 标准库，没有需要 `pip install` 的东西，也没有 lockfile 要审计。克隆下来直接读源码。
- **绝不打印/记录/存储你的 API key**：key 只从环境变量读取（**故意不提供 `--key` 参数**），所有输出都经过脱敏层。
- **刻意保持中立**：对准任何人都行——待评估的中转、官方 API、本地模型服务，或作者所在的网关（见[利益披露](#利益披露)）。工具不在乎你测谁。

## 为什么需要它

便宜的"GPT / Claude / DeepSeek"中转有一个没人明说的信任问题：有些会悄悄换成更小、量化过或被截断上下文的模型；
而且往往第一天正常、几周后你不再盯着时才开始降级。最直觉的检查还偏偏没用——

> **问模型"你是什么模型"是没用的**：那个答案来自 system prompt / 微调，极易伪造。必须测**能力与行为**，而不是自述。

## 安装与用法

```bash
git clone https://github.com/seven7763/llm-honesty-probe
cd llm-honesty-probe
python3 -m llm_honesty_probe --self-test          # 对内置 mock 运行，无需 key

export OPENAI_API_KEY="sk-...你的 key..."         # 只从环境变量读取，不进命令行历史

# 单端点
python3 -m llm_honesty_probe --base-url https://某供应商/v1 --claimed-model gpt-4o

# 差分对比（最强）：把中转和官方 API 并排 diff
python3 -m llm_honesty_probe \
  --base-url https://中转/v1 --claimed-model gpt-4o \
  --compare-base-url https://api.openai.com/v1 --compare-model gpt-4o \
  --compare-api-key-env OPENAI_API_KEY_OFFICIAL
```

## 方法论（简述）

- **分词器指纹**：不同模型族分词器不同，会通过 `usage.prompt_tokens` 泄露。对一组精心构造的字符串测 token 数，
  用"锚点差值"抵消聊天模板开销得到指纹向量。`--compare` 模式（与参考端点对比，无需参考表）最可靠；单端点则与
  由 `tiktoken` 生成的参考表（`cl100k_base` / `o200k_base`）比对，没有对应族的参考就返回"无法判定"，绝不臆测。
- **能力下限**：一组**工具已知正确答案**的题（多步算术、字符串反转、计数）+ 严格 JSON 格式 + 良性问题的拒答行为。
  旗舰模型轻松通过；降智/量化替身更易翻车。我们对"失败"赋予更高权重。
- **长上下文召回**：在长填充文本中间埋入唯一口令再让它读回——**口令由工具埋入，答案已知**。短上下文能召回、长上下文丢失，
  正是**静默截断**的典型特征。
- **稳定性与性能**：同一请求重复 N 次，看 `temperature=0` 下的确定性、`model` 字段与 `system_fingerprint` 是否稳定，
  并给出 p50/p95 延迟与错误率（仅供参考）。
- **自述身份**（低权重）：问它"你是谁"并与声称对比——因其"缺席会很可疑"才保留，但易伪造，置信度封顶为 low，绝不单独定论。

原则：`temperature=0` + 固定参数、用测量代替目测、尽量与可信参考 `--compare`、按计划定期复跑（静默降级是时间序列问题）。

## 局限

- **是信号，不是证据**：无法密码学证明权重。
- **探针集小而有主见**：知道具体探针的供应商可能针对性特判——所以最强模式是你自己掌控的差分对比，也欢迎提交更难伪造的探针。
- **计费口径有差异**：有的不返回 `usage` / 用估算 / 有计费怪癖；分词器探针带容差，宁可"无法判定"也不误判。
- **`temperature=0` 不保证确定性**，故确定性信号本就是低置信度。
- **"可疑"可能有正当原因**：小模型也许正是你要的；短上下文也许是真实上限；不同基础设施会改变延迟。用 `--compare` 消歧。

## 密钥安全

key 只从 `--api-key-env` 指定的环境变量读取（默认 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`）；没有 `--key` 参数；
没有任何代码路径会打印 key 或 `Authorization` 头；所有输出经 `redact()` 脱敏。要审计就看
`llm_honesty_probe/redaction.py` 与 `client.py`。

## 利益披露

本项目由 **daoxe**（一个 OpenAI 兼容、且为 Claude Code 原生支持 Anthropic Messages 的 LLM 网关）的作者发起。
我们做它，是因为我们希望你**去验证**供应商而不是听信宣传——**包括验证我们自己**。把它对准 daoxe 和你现在用的服务做对比：
[daoxe.com](https://daoxe.com/?utm_source=github&utm_medium=organic&utm_campaign=en_launch)。
daoxe 鼓励用户这样测它；若它没通过这些检查，那对我们就是一份想要的 bug 报告。工具的价值不依赖 daoxe，也不偏袒它。

## 相关项目

端到端评估一个端点时，两个姊妹项目可配合使用：

- **[llm-gateway-benchmark](https://github.com/seven7763/llm-gateway-benchmark)** —— 可复现的**速度/可用率**基准（成功率、p50/p95 延迟、每百万 token 价格）。它回答"这个端点快不快、贵不贵"；本工具回答"它到底是不是所声称的模型"。二者互补，而非竞争。
- **[DaoXE-AI](https://github.com/seven7763/DaoXE-AI)** —— 面向 Cursor / Claude Code / Cline 的 OpenAI/Anthropic 兼容网关接入示例（同一作者，见[利益披露](#利益披露)）。把本探针对准它，与你现在用的服务做对比。

## 许可

MIT，见 [LICENSE](LICENSE)。
