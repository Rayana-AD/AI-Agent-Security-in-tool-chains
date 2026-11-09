# 补充实验总览（未写入 main.tex · DeepSeek · bio_04 v2）

> **bio_04 v2** = 论文主配置 `idea1_provenance_mlp_bio_04`（Fold–Gate–Cleave + provenance MLP + reflection + path hard rules），并包含 **retry 通道修复**（plan 上下文、retry 样本、harness 污染判定、routing 规则）。  
> **指标约定**：Live AgentDojo 用 **Utility** 与 **Security = 1 − ASR**；Offline scripted 用 **attack block rate**（≠ Live Security，不可混表）。

**产物路径**：`runs/supplement/` · 规格：`docs/eval/OFFICIAL_ATTACK_BASELINE_SPEC.md` · 图：`runs/supplement/figures/supplement_fig*.png`

---

## 表 0 — 实验清单（做了什么、为何做、规模、结果、备注）

| ID | 类别 | 实验名称 | 目的 | 设置与规模 | 主要结果（bio_04 或焦点） | 状态 / 备注 |
|----|------|----------|------|------------|---------------------------|-------------|
| **P0** | Live peer | AgentDojo 24 cond + stress-18 | 主文同级：none / spotlight / DeBERTa / **bio_04** / Task Shield / MELON | DeepSeek-Chat；与 `configs/stress_manifest_seed.yaml` 一致；macro U/S | stress-18：**U=92.6% S=98.2%**（与 Task Shield 持平；远高于 none 38.0% S） | ✅ `p0/peer_deepseek_24cond/` |
| **P2-v2** | Offline scripted | **official_matrix_v2** | 扩展攻击几何：path、**retry**、分片、过程、MHJ 合成、LiarsBench | **193 攻击样本 × 4 配置** = 772 runs；配置含 schema_only / idea1_only / **bio_04** / bio_04_no_hard_rules | **bio_04：7 套件攻击 block 率 100%**（见表 1）；no_hard_rules 在 **state_pollution 仍 0% block** | ✅ `p2/official_matrix_v2/` |
| **P1-L3** | Live adaptive | **AutoDojo adaptive_l3_v1** | 文献 L3：optimizer 迭代改 injection，对比 static | banking · inj_0 · user_0/1 · 3 iter · 2 variants · none vs **bio_04**；OpenRouter ≈ **$0.07** | 无防 **ASR=100%**；**bio_04 ASR=0%**（static 与 autodojo cache 均未打穿）；U 因任务而异 | ✅ `p1/adaptive_l3_v1/` |
| **P1-B0** | Live static (alt bench) | **InjecAgent** | 不同 tool 组合空间（Zhan ACL’24）；非 AgentDojo 四 suite | **base** · dh 50 + ds 50 · none vs **bio_04**（Zhan 100 规模） | **ASR-valid=0%** 两者皆然；bio_04 大量 invalid（tool obs 被 fold 拦截 → 攻击链未走完） | ✅ `adaptive_matrix_v1` B0 |
| **P2-live** | Live peer defense | **IPIGuard** smoke | EMNLP’25 TDG defense 对照（非 bio_04） | workspace 1 cell · DeepSeek-V3 · important_instructions | 单 cell ASR=1（防御作对照，非 bio_04 结论） | ✅ `p2/ipiguard_live_v1/` |
| **P1-L2** | Offline white-box | **adaptive_l2_v1** | L2 动作组合（strip_envelope、cont_padding 等） | 80 episodes · **bio_04** | 聚合 ASR **0%**（路径 held-out 上多数不 binding） | ✅ `p1/adaptive_l2_v1/` |
| **P1-int** | Integration | AutoDojo / InjecAgent / IPIGuard **live smokes** | 环境与 plugin 可跑通 | 各 1–3 API cells | 全部 smoke_ok | ✅ `run_all_live_smokes.py` |
| **P1-mat** | 汇总 | **adaptive_matrix_v1** | 分轨汇总 A0/A1/B0/D | 聚合 + InjecAgent 100×2 | 见表 3–5 | ✅ `p1/adaptive_matrix_v1/report.json` |

---

## 表 1 — Offline scripted v2（attack block rate %）

**772 runs，约数分钟，无 live LLM。** 与主表 **不可数值直接对比**。

| Suite | n(攻击) | schema_only | idea1_only | **bio_04 v2** | bio_04 −hard rules |
|-------|---------|-------------|------------|---------------|---------------------|
| path_heldout | 20 | 20 | 20 | **100** | 60 |
| path_indist | 28 | 29 | 14 | **100** | 71 |
| **retry_full** | 30 | 67 | 33 | **100** | 67 |
| fragmented_shuffle | 30 | 33 | 33 | **100** | 100 |
| reflection_process | 3 | 67 | 67 | **100** | 100 |
| mhj_multihop | 20 | 100 | 100 | **100** | 100 |
| liars_bench | 40 | 100 | 100 | **100** | 100 |

**机制要点（retry_full · bio_04 v2）**

| 攻击子类 | n | bio_04 block | bio_04 −hard rules block | 解读 |
|----------|---|--------------|---------------------------|------|
| retry_abuse | 10 | 100% | 100% | retry 路径 + schema-fail 样本修复后，gate/provenance 可拦 |
| **state_pollution** | 10 | **100%** | **0%** | **routing-metadata 靠 hard rules + plan 并入 provenance** |
| fragmented | 10 | 100% | 100% | 跨节点分片 |

详见 [`RETRY_V2_FIXES.md`](RETRY_V2_FIXES.md)。

---

## 表 2 — Live AgentDojo（DeepSeek stress-18 macro）

与 **主文 Table 1 同协议**（24 manifest，macro 取 stress 子集 18 cond）。

| Defense | Utility | Security (1−ASR) | n |
|---------|---------|------------------|---|
| none | 67.6% | 38.0% | 18 |
| spotlighting | 73.2% | 53.7% | 18 |
| DeBERTa detector | 31.5% | 75.9% | 18 |
| **bio_04 v2** | **92.6%** | **98.2%** | 18 |
| Task Shield (port) | 92.6% | 98.2% | 18 |
| MELON (port) | 65.7% | 91.7% | 18 |

---

## 表 3 — L3 AutoDojo live slice（banking × 2 user tasks）

Optimizer：**3 iter × 2 variants**；Defense Security = **1 − ASR**（已从 raw log 换算）。

| Defense | Attack | n | Utility | ASR | **Defense Security** |
|---------|--------|---|---------|-----|----------------------|
| no_defense | important_instructions | 2 | 50% | 100% | 0% |
| no_defense | autodojo (optimized cache) | 2 | 50% | 100% | 0% |
| **bio_04** | important_instructions | 2 | 0% | 0% | **100%** |
| **bio_04** | autodojo | 2 | 50% | 0% | **100%** |

**解读**：文本 adaptive 在该切片 **未优于 static** 打穿 bio_04；optimizer 在 `--run-defense` 下 **3 轮 ASR 仍为 0%**。切片小，**不能替代** stress-18 或 InjecAgent 100 子集。

**成本**：optimize no_defense ≈ $0.031 + bio_04 ≈ $0.038（OpenRouter 账单）。

---

## 表 4 — Live 集成 smoke（DeepSeek）

| 基准 | 脚本 | 规模 | bio_04 相关结果 |
|------|------|------|-----------------|
| AgentDojo | `run_p1_autodojo_smoke.py` | 1 cell | plugin 注册 + 1 benchmark ok |
| InjecAgent | `run_p1_injecagent_live.py` | 3 dh / base | ASR-valid **0%**；tool obs 常 fold 拦截 |
| IPIGuard | `run_p2_ipiguard_live.py` | 1 workspace cell | 对照 defense，非 bio_04 |

---

## 表 5 — InjecAgent B0（DeepSeek · base · 已完成）

| Defense | n_valid (dh+ds) | ASR-valid | Defense Security | 备注 |
|---------|-----------------|-----------|------------------|------|
| none | 99 | **0%** | **100%** | 100 cases 中 1 invalid |
| **bio_04** | 66 | **0%** | **100%** | 34 cases invalid（多为 observation 被 guard 截断） |

**解读**：在该 InjecAgent 切片上 DeepSeek **未成功执行** attacker tool（ASR-valid=0），bio_04 与 none 数值相同，但 bio_04 **更常提前阻断 tool 返回**（valid 更少）。不等于「与 none 等价」——需看 invalid 率与 utility。Zhan **adaptive** 字符串（B2）仍待接。

---

## 表 6 — 待完成（P1 文献矩阵）

| 轨道 | 内容 | 状态 |
|------|------|------|
| B2 | Zhan NAACL’25 AdaptiveAttackAgent + bio_04 | 📋 待接 submodule |
| A0+ | AgentDojo slack static | ❌ slack 无 `injection_task_0` id（KeyError）；改 task id 后重跑 |
| C | AGENTVIGIL / IterInject | 📋 可选 |

**API 额度**：若 OpenRouter/DeepSeek 429 或余额不足，矩阵脚本会在 `report.json` 的 `errors` 中记录；已跑完部分仍保留。

---

## 可视化（论文风格）

| 图文件 | 内容 |
|--------|------|
| `supplement_fig1_live_peer.png` | Live stress-18：Utility / Security 双柱（主文同级 peers） |
| `supplement_fig2_scripted_heatmap.png` | 7 suite × 4 配置 block rate 热力图 |
| `supplement_fig3_retry_ablation.png` | retry_full 三类攻击：full bio_04 vs −hard rules |
| `supplement_fig4_l3_autodojo.png` | L3 banking 切片：ASR / Security / Utility |
| `supplement_fig5_mechanism_summary.png` | **双面板**：live 增益 + retry 通道 100% block |
| `supplement_fig6_injecagent_b0.png` | InjecAgent 100 子集：ASR-valid vs defense security |
| `p1_adaptive_*.png` | 分轨小图（A0/A1/B0/D） |
| `p2_*_v2.png` | scripted 矩阵热力图 / 扩展套件 |

生成：

```bash
./scripts/supplement.sh eval/supplement/visualize_supplement_summary.py
./scripts/supplement.sh eval/supplement/visualize_adaptive_matrix.py   # 分轨小图
./scripts/supplement.sh eval/supplement/visualize_supplement_results.py --matrix official_matrix_v2
```

---

## 汇报时建议强调的 3 点

1. **Live 双成功**：DeepSeek stress-18 上 bio_04 **U≈93% S≈98%**，相对 none 的 utility/security 双提升（表 2 · 图 1）。  
2. **Retry 侧门已关（v2）**：full bio_04 对 retry/state_pollution **100% block**；去掉 hard rules 则 state_pollution **全漏** → 机制上 **规则 + plan 上下文** 必要（表 1 · 图 3）。  
3. **Adaptive 分轨**：AutoDojo L3 小切片 **未打穿** bio_04，但需 InjecAgent/Zhan 线补全才满足文献级 adaptive claim（表 3 · 图 4；计划见 `P1_ADAPTIVE_LITERATURE_PLAN.md`）。

---

## 与主文边界

- 主文已报告：AgentDojo live static、ablation、workspace 案例图。  
- 本文档及 `runs/supplement/`：**peer 表扩展、scripted v2、L3 AutoDojo、InjecAgent/IPIGuard smoke、retry 修复验证** — 适合附录 / rebuttal / 内部对齐，**引用时需标明协议（live vs offline）**。
