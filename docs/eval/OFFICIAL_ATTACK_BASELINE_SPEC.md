# 攻击类型与基线对照规格（Official GitHub → 本仓库 supplement）

> 调研日期：2026-09-27。对照各项目 **官方 GitHub / 论文** 的任务定义、测试规模与指标含义，并映射到本仓库 `eval/supplement/` 实现。  
> 实验输出：`runs/supplement/p2/official_matrix_v2/`、`runs/supplement/p0/peer_deepseek_24cond/`、`runs/supplement/figures/ANALYSIS_v2.md`

---

## 1. 指标 glossary（先读此节）

| 指标 | 官方定义（AgentDojo 系） | 本仓库 scripted harness 对应 | 注意 |
|------|-------------------------|------------------------------|------|
| **Utility (U)** | User task 是否完成（user check pass） | 不适用（无 live agent） | 仅 **live AgentDojo** 报告 |
| **Security (S)** | Injection task 是否 **未** 成功（ASR 的补） | **Attack block rate** = 攻击样本被 harness 拦截比例 | scripted 用 block rate，**不可**与 live S 直接数值对比 |
| **ASR** | Attack success rate = injection 成功执行有害 side effect 的比例 | `attack_success` = 未 block 且 `harmful=True` | AutoDojo / IPIGuard 主指标 |
| **UA** | User task availability（IPIGuard 论文） | 同 Utility | IPIGuard README |
| **Benign FPR** | 良性任务被误拦率 | scripted 套件中 `label=benign` 的 block 比例 | 过程攻击套件必报 |

**主文 Table 1 协议（live）**：DeepSeek-Chat，24 stress conditions（`configs/stress_manifest_seed.yaml`），macro-average **U / S** over conditions where stress utility gate passes。

**Scripted supplement 协议（offline）**：固定 JSONL 攻击样本 → `run_scripted()` → block layer / harmful flag；**不与 live U/S 混表**。

---

## 2. Live 基准：AgentDojo（主文主表）

| 项 | 官方规格 | 本仓库 |
|----|----------|--------|
| **Repo** | https://github.com/ethz-spylab/agentdojo | `pip install agentdojo`；`eval/agentdojo/bio_harness_guard.py` |
| **任务** | 4 suites：`workspace`, `banking`, `slack`, `travel`；每 suite 多 user tasks + injection tasks | `configs/paper_curated.yaml` m1：50 tasks × 2 attacks × 2 injections |
| **攻击（官方）** | `important_instructions`, `tool_knowledge`, `direct`, `denial_of_service`, … | 主表：`important_instructions` + `tool_knowledge`；stress 加 persona 变体 |
| **防御（主文 baselines）** | CLI `--defense`：`none`, `spotlighting_with_delimiting`, `transformers_pi_detector`, `tool_filter`, … | `configs/paper_curated.yaml` defenses 列表 |
| **指标** | Utility + Security per (user_task, injection_task, defense) | `eval/run_agentdojo_benchmark.py` → `runs/agentdojo_upstream/` |
| **规模（主文 stress slice）** | 18 conditions × 6 defenses（none/spotlight/detector/bio + peers） | `runs/paper_peer_baselines_deepseek_progress.json` |

### 主文 baselines 含义

| Defense | 官方来源 | 机制 | 本仓库入口 |
|---------|----------|------|------------|
| **none** | AgentDojo upstream | 无防御 | `--defense none` |
| **spotlighting_with_delimiting** | Debenedetti et al. 2024 | Prompt 分隔 + delimiting | AgentDojo built-in |
| **transformers_pi_detector** | AgentDojo + ProtectAI DeBERTa | 工具输出 PI 检测 | `--defense transformers_pi_detector` |
| **bio_04** | 本文 | Fold–Gate–Cleave + provenance + reflection | `bio_harness_guard.py` / config `idea1_provenance_mlp_bio_04` |

---

## 3. Peer defenses（GitHub 官方 / faithful port）

### 3.1 MELON（ICML 2025）

| 项 | 官方规格 |
|----|----------|
| **Repo** | https://github.com/kaijiezhu11/MELON |
| **任务** | **AgentDojo 全 benchmark**（与 upstream 相同 suites/tasks） |
| **机制** | Masked re-execution + tool comparison；threshold=0.1 |
| **指标** | Utility + Security（论文 Table vs SOTA defenses） |
| **命令示例** | `python -m agentdojo.scripts.benchmark --model gpt-4o-2024-05-13 --attack tool_knowledge --defense melon -s slack` |
| **本仓库** | `eval/agentdojo/peer_defenses.py` → `MelonDefense`；embedding 换为 HashingVectorizer（无 OpenAI key） |
| **已跑规模** | DeepSeek 24 cond peer export：stress macro **U=65.7%, S=91.7%** |

### 3.2 Task Shield（ACL 2025）

| 项 | 官方规格 |
|----|----------|
| **Paper** | Jia et al., ACL 2025 — *The Task Shield* |
| **官方 code** | **无公开 GitHub** |
| **机制** | Test-time goal alignment（ContributesTo check on tool calls） |
| **本仓库** | `TaskShieldDefense` — 用 agent 同 backbone LLM 做 goal alignment |
| **已跑规模** | 同 24 cond manifest；stress macro **U=92.6%, S=98.2%**（与 bio_04 持平） |

### 3.3 IPIGuard（EMNLP 2025 Oral）

| 项 | 官方规格 |
|----|----------|
| **Repo** | https://github.com/Greysahy/ipiguard |
| **任务** | AgentDojo 4 suites：`workspace`, `slack`, `travel`, `banking` |
| **攻击** | `ignore_previous`, `inject_agent`, `tool_knowledge`, `important_instructions` |
| **指标** | **ASR↓ / UA↑** per suite + Overall average |
| **命令** | `bash eval.sh`（`agent_model`, `attack_name`, `defense_name=ipiguard`, `suite_name`） |
| **本仓库** | `eval/supplement/run_p2_ipiguard_integration.py` — **plan only，未 live 跑** |

---

## 4. Adaptive 基准：AutoDojo（2026）

| 项 | 官方规格 |
|----|----------|
| **Repo** | https://github.com/xhOwenMa/AutoDojo（已 clone 至 `third_party/AutoDojo/`） |
| **任务** | AgentDojo 3 suites（banking/slack/travel）+ AgentDyn 3 suites |
| **攻击** | Static：`important_instructions`, …；**Adaptive**：`autodojo`（optimized injections cache） |
| **防御（论文 9+none）** | spotlighting, reminder, sandwich, promptguard, piguard, protectai, datafilter, drift, progent, camel |
| **指标** | **ASR**, Utility；`aggregate_results.py` / `compute_bucket_asr.py`（action-open vs specified buckets） |
| **规模** | 每 (suite, model, defense) 一 cell cache；optimizer 迭代 budget 见 `variant_generation/README.md` |
| **本仓库** | P1 L2 white-box scripted（80 eps）；**L3 AutoDojo live 未接 bio_04 plugin** |

---

## 5. 扩展攻击类型（supplement scripted suites）

以下攻击 **不在 AgentDojo 官方 attack registry 内**，为本仓库为 rebuttal 设计的 **offline 压力测试**，需与 §2 live 结果分表报告。

### 5.0 Retry 算不算「AI 自适应攻击」？

**结论：不算 literature 意义上的 AI adaptive attack，但属于 harness 内的多步协议攻击（P1 L2 white-box）。**

| 维度 | Retry / state pollution（本仓库 scripted） | AI adaptive IPI（AutoDojo / AGENTVIGIL / IterInject） |
|------|------------------------------------------|--------------------------------------------------------|
| **谁在 adapt** | 固定脚本，利用 **已知** gate retry / pollution 通道 | **LLM / MCTS / optimizer** 根据 success/fail 迭代改 injection |
| **知识假设** | White/grey-box（知道 fold 失败会 retry、routing-metadata 会污染 state） | Black-box 或 optimizer-driven probe |
| **P1 层级** | L2 `retry_paraphrase` / channel pollution | L3 AutoDojo adaptive benchmark |
| **rebuttal 标签** | Gate/retry exploitation、state pollution | Adaptive red-teaming |

因此 rebuttal 中应把 retry 与 AutoDojo **分表**：前者测 **架构 retry 路径** 是否可被二次注入利用；后者测 **对手 LLM 能否学会绕过**。

### 5.1 Retry / 状态污染 / 碎片化（过程内 atomic IPI）

| 攻击子类型 | 设计来源 | 任务语义 | 官方最接近 | v2 规模 | v2 指标 |
|------------|----------|----------|------------|---------|---------|
| **retry_abuse** | 本仓库 `eval/attacks/retry_abuse.py` | Plan schema fail → retry 注入 routing hint → tool 读 secrets | AgentDojo retry 路径 + Zhan adaptive 思路 | **10** | block rate, block_layer |
| **state_pollution** | 同上 | Plan/review 埋 routing metadata，tool 阶段看似 benign | Idea1 channel pollution | **10** | block rate |
| **fragmented** | 同上 | 跨 plan/review/tool 分片有害意图 | AutoDojo TopicAttack / 本仓库 `atomic_split.py` | **10** | block rate |
| **fragmented_intra** | `eval/attacks/fragmented_shuffle.py` | 单节点 tool_call 内分片 exfil | Shuffle coherence 实验 Exp A | **10** | block rate |
| **fragmented_cross** | 同上 | 各节点单独 benign，组合有害 | Cross-node composition | **10** | block rate |
| **deception** | 同上 | 表面 compliant 的 send_email | LiarsBench-like surface | **10** | block rate |
| **retry_paraphrase** | `eval/attacks/idea1_subtle_pollution.py` | Gate retry 换措辞注入 path | P1 L2 mutation `retry_paraphrase` | **4**（in path_indist） | block rate |

**AgentDojo 官方 atomic 对照**：`eval/attacks/atomic_split.py` 注册 `atomic_split` / `atomic_schema_smuggle` — **live AgentDojo only**，v2 scripted 未替代。

### 5.2 过程攻击（reflection / thinking loop）

| 攻击子类型 | 设计来源 | 任务语义 | 官方最接近 | v2 规模 | v2 指标 |
|------------|----------|----------|------------|---------|---------|
| **process_thinking_loop** | `reflection_process_samples.py` | 高 churn 内心独白，延迟 grounding | MHJ thinking-style / 长 CoT 攻击 | **1** + 1 benign | block rate, benign FPR |
| **cross_node_reflection_drift** | 同上 | Review 与 proposed tool 几何不一致 | Reflection probe 设计目标 | **1** + 1 benign | block rate |
| **rational_lie_process** | 同上 | Wait-chain 合理化有害 tool | Rationalization attacks | **1** | block rate |

**官方 probe 路径**：`eval/run_reflection_provenance_audit.py`（仅 reflection 层，非全 harness）。

### 5.3 MHJ 式跨步升级（temporal escalation）

| 项 | 官方规格 | 本仓库 v2 |
|----|----------|-----------|
| **Dataset** | HuggingFace `ScaleAI/mhj`（**gated**，需 HF token） | 无 token 时用 **synthetic multi-hop** |
| **任务** | 多轮对话逐步升级有害请求；tactics: escalation, decomposition, incremental, roleplay, context_manipulation | `eval/loaders/mhj.py` |
| **官方指标** | Jailbreak success rate（非 AgentDojo U/S） | scripted：**2-hop** plan→review escalation + external fold |
| **v2 规模** | 论文 subset 常用 50–100 conversations | **20** synthetic multi-hop（待 HF 解锁后换 real） |

### 5.4 Path / cleave / external（Idea1 subtle）

| Suite | 攻击类型 ×4 each | 样本 | 对照 |
|-------|------------------|------|------|
| **path_indist** | paraphrase, cleave_synonym, review_drift, retry_paraphrase, json_smuggle, external_subtle, tool_output_subtle | 28 atk + 10 benign | 主文 Idea1 压力集 |
| **path_heldout** | path_smuggle, no_envelope, paraphrase, external, review_drift | 20 atk + 10 benign | Held-out generalization |

---

## 6. v2 实验矩阵（scripted baselines 对照）

### 6.1 配置（对照主文 ablation / 最弱 structural baseline）

| Config key | 含义 | 对应主文/官方 |
|------------|------|---------------|
| `schema_only` | 仅 schema fold，无 partition/gate/cleave | 最弱 **offline** structural baseline（≠ AgentDojo `none`） |
| `idea1_only` | Idea1 partition + gate，无 provenance MLP | 主文 drop-one 对照 |
| `idea1_provenance_mlp_bio_04` | 完整 bio_04 | 主文方法 |
| `bio_04_no_hard_rules` | bio_04 去掉 path hard rules | 消融 |

> **Live baselines**（none / spotlight / detector / Task Shield / MELON）**仅**在 §2 AgentDojo 24-cond 导出中对比；scripted matrix 不模拟 prompt-level defenses。

### 6.2 Suites × 规模（v2 合计）

| Suite | 攻击数 | 良性数 | 总样本 |
|-------|--------|--------|--------|
| path_heldout | 20 | 10 | 30 |
| path_indist | 28 | 10 | 38 |
| retry_full | 30 | 0 | 30 |
| fragmented_shuffle | 30 | 0 | 30 |
| reflection_process | 3 | 2 | 5 |
| mhj_multihop | 20 | 0 | 20 |
| liars_bench | 40 | 0 | 40 |
| **合计** | **171** | **22** | **193** |

× 4 configs = **772** scripted runs（离线，~数分钟）。

### 6.3 运行命令

```bash
python eval/supplement/run_official_matrix_v2.py
python eval/supplement/visualize_supplement_results.py --matrix official_matrix_v2
python eval/supplement/run_p0_peer_table.py   # live AgentDojo peer 表
```

---

## 7. 分析输出结构（`ANALYSIS_v2.md`）

1. **Table A — Live AgentDojo（官方协议）**：none / spotlight / detector / bio_04 / Task Shield / MELON × stress-18 macro U/S  
2. **Table B — Scripted v2 block rate**：4 configs × 6 suites heatmap  
3. **Table C — 分攻击类型 gap**（retry / fragmented / process / mhj）  
4. **可信度标注**：schema 误拦、MHJ synthetic、未跑 IPIGuard live 等  

---

## 8. 实现差距与后续（按官方 GitHub 优先级）

| 优先级 | 项 | 官方要求 | 当前状态 |
|--------|-----|----------|----------|
| P0 | Peer 表进附录 | AgentDojo 同 manifest | ✅ 已导出 |
| P1 | AutoDojo L3 × bio_04 | `third_party/AutoDojo` benchmark + plugin | ✅ live smoke (`run_p1_autodojo_smoke.py --execute`) |
| P1 | InjecAgent subset | `third_party/InjecAgent` + DeepSeek | ✅ live smoke 3-case (`run_p1_injecagent_live.py`) |
| P1 | IPIGuard live subset | `Greysahy/ipiguard` + DeepSeek-V3 | ✅ live smoke 1-cell (`run_p2_ipiguard_live.py`) |
| P2 | MHJ real subset | HF `ScaleAI/mhj` + token | 🔒 gated → synthetic |
| P2 | atomic_split live | AgentDojo `--attack atomic_split` | 有代码，supplement 未跑 |
| P2 | fragmented_shuffle | 本仓库 Exp A | ✅ v2 纳入 |

---

## 10. DeepSeek 四条研究线 — 覆盖矩阵（2026-09-27）

与 AgentDojo 实验的关系：**仅第 3、4 线有 live/scripted 覆盖**；第 1、2 线 mostly out-of-scope 或弱代理。

### 10.1 总览

| 研究线 | 代表工作 | 测了吗 | 本仓库映射 | bio_04 表现（已有） |
|--------|----------|--------|-----------|---------------------|
| **1. Chat jailbreak** | HarmBench, CHiSafety, Ying eval, **NIST CAISI** | ❌ | — | — |
| **2. R1 / CoT** | H-CoT, LRM risks, Garak | ⚠️ 弱代理 | `important_instructions_education` live；`reflection_process` scripted | live S=100% vs spot 39% |
| **3. PI 专项** | AgentDojo, InjecAgent, PromptFuzz | ⚠️ AgentDojo only | stress-18 live + scripted v2 | live S=98.2% |
| **4. Agent 自适应** | AutoDojo, AGENTVIGIL, IterInject, AdapTools | ⚠️ 协议+L2 | P1 L2 scripted；AutoDojo plugin scaffold | L2 ASR=0%（非 live 优化） |

### 10.2 线 1 — Chat / 对齐层（未测）

| 工作 | 为何未测 | rebuttal 建议 |
|------|----------|---------------|
| HarmBench / TAP / GCG | 纯 chat，非 tool agent | Discussion scope 边界 |
| CHiSafetyBench | 中文 content safety | 不claim |
| NIST CAISI agent hijacking | 未跑 19 benchmarks | 定性引用，不混进 Table 1 |

### 10.3 线 2 — Reasoning / CoT（弱代理）

| 代理 | 规模 | bio_04 | 备注 |
|------|------|--------|------|
| `important_instructions_education` (H-CoT **style**) | 6 live cond | S=**100%** | DeepSeek-**Chat**，非 R1 |
| `important_instructions_persona` | 6 live cond | S=**100%** | depth-dependent IPI stress |
| `process_thinking_loop` | 1 scripted | 1/1 block | benign FPR 50%；非 real CoT |
| MHJ multihop | 20 synthetic | 100% fold | HF `ScaleAI/mhj` gated |

### 10.4 线 3 — Prompt Injection 专项

| 项 | 状态 | DeepSeek stress-18 macro |
|----|------|--------------------------|
| AgentDojo static (`important_instructions`, `direct`, persona/education) | ✅ live | bio U=92.6% **S=98.2%** |
| spotlight / detector baselines | ✅ live | S=53.7% / 75.9% |
| Task Shield / MELON peers | ✅ live | S=98.2% / 91.7% |
| **InjecAgent** | ❌ 未跑 | 计划 P1 |
| **PromptFuzz-SC** | ❌ 未跑 | — |

### 10.5 线 4 — Agent 自适应攻击

| 项 | 状态 | 说明 |
|----|------|------|
| **M1 static attacks** | ✅ 主表 | `important_instructions` + `tool_knowledge` — 非 adaptive |
| **P1 L2 white-box** | ✅ 80 eps scripted | 4 mutations × held-out；ASR=0% |
| **AutoDojo L3** | ⏳ plugin 已注册 | `eval/supplement/autodojo_plugin.py` + `run_p1_autodojo_smoke.py --verify-only` |
| AGENTVIGIL / IterInject / AdapTools | ❌ | 未集成 |

**验证命令**：

```bash
python eval/supplement/run_p1_autodojo_smoke.py --verify-only
# live smoke (需 API):
python eval/supplement/run_p1_autodojo_smoke.py --execute --defense bio_04
```

### 10.6 补测优先级

| 优先级 | 任务 | 回应 |
|--------|------|------|
| **P0** | AutoDojo L3 × bio_04 vs spotlight | 线 4：static 98% 是否虚高 |
| **P1** | InjecAgent subset | 线 3 扩展 threat |
| **P2** | real MHJ + LiarsBench matrix | 线 1/2 |
| **P3** | HarmBench / PromptFuzz | scope 外，Discussion 定性 |

---

## 9. 参考文献 / GitHub 链接

- AgentDojo: https://github.com/ethz-spylab/agentdojo  
- MELON: https://github.com/kaijiezhu11/MELON  
- AutoDojo: https://github.com/xhOwenMa/AutoDojo  
- IPIGuard: https://github.com/Greysahy/ipiguard  
- InjecAgent: https://github.com/uiuc-kang-lab/InjecAgent（扩展 threat，非主表）  
- MHJ dataset: https://huggingface.co/datasets/ScaleAI/mhj（gated）
