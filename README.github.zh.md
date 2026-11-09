# 工具链场景下的 AI Agent 安全

在工具调用型 Agent 中，不可信的工具返回值可能携带 **间接提示注入（IPI）**，影响后续推理或触发越权操作。本仓库提供可插拔的 **Fold → Gate → Cleave** 边界协议及跨轮 episode 状态，**无需**对骨干模型做微调。

[English README](README.en.md)

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

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,agentdojo]"
```

在线实验前复制密钥模板（文件已 gitignore）：

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
```

在 `configs/secrets.yaml` 中填写至少一种后端密钥（例如 `deepseek_api_key` 或 `huggingface_api_key`）。模型优先级与路由见 `configs/model.yaml`；`model_mode: auto` 时会按 `model_priority` 依次尝试可用提供商。

---

## 5 分钟自检（无需 API）

用于确认环境与本仓库配置键一致：

```bash
pytest -q
```

预期：测试全部通过（约一两分钟，视机器而定）。

---

## 路径 1：离线结构攻击矩阵（推荐入门）

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

## 路径 2：AgentDojo 在线基准

### 准备 AgentDojo 源码

`eval/run_agentdojo_benchmark.py` 会把下面路径加入 `PYTHONPATH`（与 PyPI 安装的 `agentdojo` 并不完全等价）：

```text
third_party/AutoDojo/agentdojo/src
```

完整克隆本仓库且包含 `third_party/AutoDojo` 时可直接使用。若目录缺失，请按 [`eval/supplement/AUTODOJO_INTEGRATION.md`](eval/supplement/AUTODOJO_INTEGRATION.md) 拉取 vendored 版本（推荐固定文档中的 commit）。

### 冒烟运行

确认 `configs/secrets.yaml` 可用后：

```bash
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

## 路径 3：接入自有 AgentDojo Pipeline

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

## 评测结果概览

以下为仓库内脚本可复现的趋势摘要；**具体数值取决于模型与 manifest**，以你本地 `runs/` 下生成的 JSON 为准。

| 评测 | 脚本 | 概要 |
|------|------|------|
| AgentDojo 多套件 + 压力切片 | `run_agentdojo_benchmark.py`、`run_m1_manifest_seed.sh` | 完整栈在报告配置下可达高 macro security，并通过 inbound 修复与 continuity 缓解「只拦不修」带来的 utility 坍塌。 |
| 离线 7 套件矩阵 | `run_official_matrix_v2.py` | 仅 schema 对路径走私、重试通道污染等不足；带 path 规则的完整栈显著提升 block rate。 |
| AgentVigil 等 supplement | `eval/supplement/run_golorial_agentvigil_slice.py` 等 | 自适应搜索得到的 payload 重放；inline 渗出类场景可能优先安全。 |

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
