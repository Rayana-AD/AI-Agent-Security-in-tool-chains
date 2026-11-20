# 工具链场景下的 AI Agent 安全

在工具调用型 Agent 中，不可信的工具返回值可能携带 **间接提示注入（IPI）**，影响后续推理或触发越权操作。本仓库提供可插拔的 **Fold → Gate → Cleave** 边界中间件及跨轮 episode 状态，**无需**对骨干模型做微调。

[English README](README.en.md)

> ### 30 秒摘要
>
> | | |
> |---|---|
> | **做什么** | 在「工具返回 → 模型」和「模型 → 工具调用」两处加护栏：可疑入站输出可去毒或扣留，危险出站调用可拦截；多轮任务记住是否曾被污染。 |
> | **公开结果（AgentDojo）** | DeepSeek-Chat **stress-18**：安全 **38.0% → 100%**，任务完成 **67.6% → 92.6%**；24 格全 conditions 上 DeepSeek 与 Llama-3-70B 均为 **100%** 安全（Llama stress 效用 **64.6%**，受模型规划能力限制）。离线结构逃逸 **111** 个 attack 子集上完整栈 **100%** 拦截。 |
> | **你怎么用** | 已有 Agent 循环：接入 Guard / `build_pipeline("bio_04", …)`；只想验证：下面「最快上手」两条命令，**不需要 API 密钥**。 |
>
> 数字出自论文稿与仓库脚本可复现配置；本地重跑以 `runs/` 下 JSON 为准。

---

## 你能用这个仓库做什么

1. **接进现有 Agent 框架（中间件）** — 在工具结果进入 LLM 前、在工具调用发出前插入本仓库的 Guard；与 LangChain / 自研循环 / AgentDojo `AgentPipeline` 均可对接（见下文 **路径 C**）。
2. **用固定样本压测边界协议（免 API）** — 离线矩阵几分钟内给出 block rate，适合 CI 或改配置后的回归。
3. **对齐 AgentDojo 主表（需 API）** — 冒烟一条 episode 或跑 manifest；密钥只在本地 `configs/secrets.yaml`，不进 git。

---

## 最快上手（三选一）

| 耗时 | 目标 | 命令 |
|------|------|------|
| **~2 分钟** | 确认环境 | `pip install -e ".[dev]"` 后 `pytest -q` |
| **~3–5 分钟** | 单测 + 一条离线防御曲线（推荐首次克隆） | `./scripts/github_quickstart.sh` |
| **~5 分钟** | 真模型连通性（需密钥） | 见下方 **路径 B → 冒烟运行** |

完整安装与三条深入路径见下文；**不必一次跑完全部评测脚本**。

---

## 背景

Agent 会通过工具读取邮件、文件、目录和第三方 API。攻击者常把指令藏在「看起来像正常数据」的返回里。只靠系统提示让模型「忽略不可信内容」，在伪装良好的注入面前不稳定；若采用无脑拦截，又容易把完成任务所需的列表、字段一并删掉。

## 方法

协议工作在两类边界上：**工具输出进入模型**（inbound）与 **模型发起工具调用**（outbound）。

| 阶段 | 作用 |
|------|------|
| **Fold** | 将输出整理为 typed 字段；打乱字段顺序并检查语义/归因是否异常；provenance 分类器与 reflective 探针给出风险与流向信号。 |
| **Gate** | 读、写不对称：观察类 inbound 可在修复后放行；高后果 outbound 需与用户目标连续（continuity）。episode store 记录本任务是否曾遭污染。 |
| **Cleave** | 若恶意指令包在「信封」里、任务数据在「货物」里，剥离信封并保留货物，避免为安全而牺牲可完成的任务字段。 |

可选 **Elastic** 在探测到异常交互时加强 shuffle 等检查强度。

- 核心库：`src/bio_harness/`（pip 包名 `bio-harness`）
- AgentDojo 管线挂钩：`eval/agentdojo/bio_harness_guard.py`、`pipeline_factory.py`

---

## 环境要求

| 用途 | Python | 依赖 | 其他 |
|------|--------|------|------|
| 单元测试、离线攻击矩阵 | ≥ 3.10 | `pip install -e ".[dev]"` | 无 API |
| AgentDojo 在线评测 | ≥ 3.10 | `pip install -e ".[dev,agentdojo]"` | `configs/secrets.yaml` + 见下文 AgentDojo 源码路径 |
| 部分 supplement 直播实验 | ≥ 3.10 | `pip install -e ".[supplement-live]"` | 额外 third_party（见各脚本说明） |

---

## 安装

```bash
git clone https://github.com/Rayana-AD/AI-Agent-Security-in-tool-chains.git
cd AI-Agent-Security-in-tool-chains
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"          # 离线矩阵 + 单测
# pip install -e ".[dev,agentdojo]"  # 需要 AgentDojo 在线评测时再装
```

**只有要调用真实模型时**再配置密钥（已 gitignore）：

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
# 填写 deepseek_api_key 或 huggingface_api_key 等；路由见 configs/model.yaml
```

---

## 路径 A：离线结构攻击矩阵（免 API，推荐第二站）

不调用外部 LLM，用脚本化 harness 在固定 JSONL/生成样本上跑 Fold–Gate–Cleave。

```bash
python eval/supplement/run_official_matrix_v2.py
```

默认在 7 个套件 × 4 套配置上运行（`schema_only`、`idea1_only`、`idea1_provenance_mlp_bio_04`、`bio_04_no_hard_rules`），套件包括路径 heldout、重试滥用、分片 shuffle、reflection 流程等。

**输出位置：** `runs/supplement/p2/official_matrix_v2/matrix_summary.json`（各 cell 明细在同目录下 `cells/`）。

**快速试跑单个套件（缩短时间）：**

```bash
python eval/supplement/run_official_matrix_v2.py \
  --suites path_heldout \
  --configs idea1_provenance_mlp_bio_04
```

**在代码里单独加载协议：**

```python
from bio_harness.harness.graph import build_runner

runner = build_runner("idea1_provenance_mlp_bio_04")
# 与 eval/scripted_runner.py 相同配置来源：configs/ablations.yaml
```

其他离线审计（可选）：

```bash
python eval/run_bio04_config_audit.py
python eval/run_provenance_generalization_audit.py
python eval/run_agentdojo_utility_bounds_audit.py
```

---

## 路径 B：AgentDojo 在线基准（需 API）

### 准备 AgentDojo 源码

`eval/run_agentdojo_benchmark.py` 会把下面路径加入 `PYTHONPATH`（与 PyPI 安装的 `agentdojo` 并不完全等价）：

```text
third_party/AutoDojo/agentdojo/src
```

完整克隆本仓库且包含 `third_party/AutoDojo` 时可直接使用。若目录缺失，请按 [`eval/supplement/AUTODOJO_INTEGRATION.md`](eval/supplement/AUTODOJO_INTEGRATION.md) 拉取 vendored 版本（推荐固定文档中的 commit）。

### 冒烟运行

确认 `configs/secrets.yaml` 可用后：

```bash
pip install -e ".[dev,agentdojo]"
python eval/run_agentdojo_benchmark.py --smoke \
  --model-mode deepseek \
  --defense none --defense bio_04
```

说明：

- `--smoke`：默认 `workspace`、`user_task_0`、2 个 injection task；适合连通性检查。
- 完整协议在管线中的别名为 **`bio_04`**，对应配置键 **`idea1_provenance_mlp_bio_04`**。
- 日志与汇总：`runs/agentdojo_upstream/benchmark_<时间戳>/report.json`。

**指定防御与套件示例：**

```bash
python eval/run_agentdojo_benchmark.py \
  --suite workspace --suite banking \
  --defense none --defense spotlighting_with_delimiting --defense bio_04 \
  --model-mode deepseek
```

### 压力 manifest（小规模试跑）

```bash
./scripts/run_m1_manifest_seed.sh 1 1
```

完整 24 batch 耗时长、产生 API 费用；`1 1` 仅跑第 1 个 batch。防御列表见 `configs/stress_manifest_seed.yaml`（含 `bio_04`）。

---

## 路径 C：接入自有 AgentDojo Pipeline（中间件）

在已有 `AgentPipeline` 项目中，用工厂函数挂载本仓库防御（需能 import `agentdojo` 与 `eval.agentdojo`）：

```python
from eval.agentdojo.pipeline_factory import build_pipeline, resolve_llm

llm, llm_name, provider = resolve_llm("deepseek")
pipeline = build_pipeline("bio_04", llm, llm_name, provider=provider)
# pipeline 内顺序：EpisodeReset → LLM → PreToolGuard → ToolsExecutor → ToolGuard → LLM
```

管线元素（可自行组合时参考）：

- `BioHarnessToolGuard` — inbound 工具输出边界
- `BioHarnessPreToolGuard` — outbound 调用前 Gate
- `BioHarnessEpisodeReset` — 新 episode 清空 carry

`build_pipeline` 的 `defense` 字符串与内部配置键映射见下表；修改行为请编辑 `configs/ablations.yaml` / `configs/paper_experiments.yaml` 中对应块，而不是改 guard 源码。

---

## 配置与防御别名

| 管线 `defense` 名 | Harness 配置键 | 典型用途 |
|-------------------|----------------|----------|
| `bio_04` | `idea1_provenance_mlp_bio_04` | 当前默认完整栈 |
| `bio_remeasure` | `idea1_provenance_mlp_bio_remeasure` | 与主表重测对齐的 carry/部署细节 |
| `bio_04_minus_hard_rules` | 同名（`paper_experiments.yaml`） | 关闭 path 类硬规则（消融） |
| `bio_04_no_hard_rules` | 同名（`ablations.yaml`） | 离线矩阵中的「无 path 规则」对照 |
| `bio_04_main_historical` | `paper_main_historical.yaml` | 复现较早部署（含历史 carry 天花板等行为） |

逐字段开关（schema fold、feature shuffle、cleave 等）均在上述 YAML 的 `defenses.<name>` 节点中。

---

## 评测结果概览（论文主结论，可脚本复现）

**AgentDojo live**（`merged_deepseek.json` / `merged_llama.json` 口径，stress 条件宏平均）：

| 模型 | 防御 | Stress 效用 / 安全 | 备注 |
|------|------|-------------------|------|
| DeepSeek-Chat | 无 | 67.6% / 38.0% | stress-18 |
| DeepSeek-Chat | BioHarness | **92.6% / 100%** | unfiltered 效用 94.4% |
| Llama-3-70B | 无 | 47.9% / 39.6% | 容量消融 |
| Llama-3-70B | BioHarness | **64.6% / 100%** | banking 多步受模型能力限制 |

**离线结构矩阵**（`official_matrix_v2`，discriminating 111 attacks）：完整 BioHarness 在五类非 envelope 套件上 **100%** attack block rate；仅 schema 约 **20–67%**（因套件而异）。

**自适应红队**（AgentVigil banking，9 goals）：MCTS 攻破无防御 **3/9** 元数据渗出目标；同一 payload 对 BioHarness 重放 **全部拦截**（付账单子任务上用户检查可能失败，与内联污染几何有关）。

本地重跑：manifest / 离线矩阵脚本；**以你 `runs/` 产出为准**。

---

## 仓库布局

```text
src/bio_harness/          # Fold / Gate / Cleave、provenance、carry
eval/agentdojo/           # AgentDojo guards 与 pipeline 工厂
eval/supplement/          # 离线矩阵、自适应实验
configs/                  # 防御配置与 benchmark 清单
data/attacks/             # 离线样本与生成器输入
models/                   # provenance MLP 权重（JSON）
tests/
```

---

## 许可证

请查看仓库根目录 `LICENSE`（若尚未添加，以仓库最新提交为准）。AgentDojo、AutoDojo 等第三方组件适用其各自许可证。