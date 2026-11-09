# P1 Adaptive 攻击：文献对照与新方案（v2）

> 目的：不只依赖 AutoDojo 改 injection 文案，而是对齐 **经典 + 近期** adaptive IPI 论文的 **威胁模型、预算、指标、基准切片**，再映射到 BioHarness（live AgentDojo + InjecAgent + 可选 AGENTVIGIL/IterInject）。

相关：`P1_ADAPTIVE_REDTEAM_PROTOCOL.md`（L0–L3 分层）、`GITHUB_REDTEAM_SURVEY.md`、`OFFICIAL_ATTACK_BASELINE_SPEC.md` §5.0。

---

## 1. 文献里「adaptive」分别指什么

| 工作 |  venue / code | 攻击者能力 | 典型预算 | 主基准 | 成功定义 |
|------|---------------|------------|----------|--------|----------|
| **InjecAgent** (Zhan et al., ACL 2024 Findings) | [Anthology](https://aclanthology.org/2024.findings-acl.624/) · [GitHub](https://github.com/uiuc-kang-lab/InjecAgent) | **Static** 攻击指令嵌在 tool 返回；`enhanced` 加 hacking prompt | 1054 cases；论文子集常用 **100**（50 DH + 50 DS） | 自建 user×attacker tool 组合 | ASR-valid / ASR-all |
| **Adaptive Attack Agent** (Zhan et al., NAACL 2025 Findings) | [Anthology](https://aclanthology.org/2025.findings-naacl.395/) · AdaptiveAttackAgent | **Adaptive 字符串**：针对各 defense **定制** adversarial suffix / 改写 | 100-case InjecAgent 子集 × **8 defenses** | InjecAgent subset | ASR **>50%** 打穿多种 defense |
| **AutoDojo** (Ma et al., 2026) | [AutoDojo](https://github.com/xhOwenMa/AutoDojo) | Optimizer LLM **迭代改 wrapper/injection**；seed 含 rlhammer/topicattack | 每 (suite, model, defense) 一 cell；iterations 可配 | AgentDojo + AgentDyn suites | ASR under `--run-defense` |
| **AGENTVIGIL** (Wang et al., EMNLP 2025 Findings) | Anthology · 公开 repo | **Black-box MCTS** 选 seed、变异 contextual injection | MCTS rollouts（论文级） | **AgentDojo + VWA-adv** | Agent task 被劫持 / 有害动作 |
| **IterInject** (2026 预印本，spec 中引用) | 待 pin commit | **Structured feedback** + 迭代 payload | 与 AGENTVIGIL / static 对比 | AgentDojo、InjecAgent | 报告优于 static & AGENTVIGIL |

**本仓库已跑 / 已接：**

- AgentDojo live 主表（L0 static）✅  
- AutoDojo L3 smoke + banking 小切片 ✅（`runs/supplement/p1/adaptive_l3_v1/`）  
- InjecAgent live smoke + bio_04 guard ✅  

**尚未作为「adaptive 主 claim」接入：** AdaptiveAttackAgent 全流程、AGENTVIGIL、IterInject。

---

## 2. 为什么不能只改 AutoDojo

1. **基准覆盖不同**：InjecAgent 测 **tool 组合空间**（17 user tools × 62 attacker tools），不是 AgentDojo 四个 suite；Zhan 2025 adaptive 主要在 **InjecAgent 100 子集** 上打 defense。  
2. **adapt 机制不同**：AutoDojo = 文本 optimizer + ASR 反馈；AGENTVIGIL = MCTS；Zhan adaptive = **per-defense 对抗串**（更接近「知道 defense 类别」的 grey-box）。  
3. **审稿预期**：仅报 AutoDojo 易被说成「只防 envelope 类改写」；需至少 **两条独立 adaptive 线**（建议：**InjecAgent/Zhan 线 + AgentDojo/AutoDojo 线**）。

AutoDojo 仍保留为 **AgentDojo 生态内** 的标准 adaptive baseline，但不作为唯一证据。

---

## 3. 推荐新方案：`P1_adaptive_matrix_v1`

### 3.1 设计原则

- **同一 defense 栈**：`none`、`spotlighting`、`bio_04`（+ 可选 `task_shield` 作 peer）。  
- **同一 backbone**：DeepSeek-Chat（与主表一致）。  
- **分轨报告**，禁止与 scripted retry（L2）混表。  
- **合理规模**（非 rebuttal-max）：每条轨先 **smoke → paper slice**，再决定是否 full。

### 3.2 轨道 A — AgentDojo / AutoDojo（已有基础）

| 阶段 | 设置 | 对齐文献 |
|------|------|----------|
| A0 Static | `important_instructions` + `tool_knowledge` | AgentDojo 主表 |
| A1 AutoDojo optimizer | banking/slack + **主文 manifest 子集** user tasks；3–5 iter；`--run-defense` | Ma et al. AutoDojo |
| A2 可选 workspace | 给 `optimize_variants.py` 补 `workspace` SUITE_CONFIG | 与主文 Figure 1 对齐 |

**指标（统一换算）**：从 AgentDojo 原始 log 的 `security` 字段转为 **Defense Security = 1 − ASR**（`security=true` 在 raw log 里表示 **injection 成功**）。

**已观察（banking × 2 user tasks）**：no_defense ASR≈100%；bio_04 ASR≈0%（static 与 autodojo cache 均未打穿）。**不能外推 full stress-18**。

### 3.3 轨道 B — InjecAgent + Zhan-style adaptive（优先补全）

| 阶段 | 设置 | 对齐文献 |
|------|------|----------|
| B0 Static | InjecAgent `base` setting，N=50–100 子集（与 Zhan 2025 同规模） | InjecAgent paper |
| B1 Enhanced | `enhanced` + hacking prompt（上界参考） | InjecAgent |
| B2 Adaptive | 接 **AdaptiveAttackAgent** 或复现其 **per-defense adversarial string** 流程 | Zhan NAACL 2025 |

**Defense 接入**：  
- `none`：无 guard  
- `bio_04`：已有 `run_p1_injecagent_live.py` tool-output guard（需声明与 AgentDojo pipeline 差异）  
- 可选：spotlighting 类 prompt 分隔（若 InjecAgent 模板支持）

**指标**：ASR-valid（主）、utility/任务完成（若 benchmark 提供）。

### 3.4 轨道 C — AGENTVIGIL 或 IterInject（二选一，中期）

| 条件 | 动作 |
|------|------|
| 有 GPU / 长跑预算 | Clone AGENTVIGIL，注册 AgentDojo pipeline + bio_04 plugin，**stress-18 子集** MCTS budget 对齐论文 smoke |
| 更轻 | 仅引 IterInject 公开脚本对 **同一 stress 子集** 跑 fixed iterations，与 A1 对比 |

**成功标准**：相对 static ASR 提升 ΔASR；bio_04 下 **Security 下降是否显著**（bootstrap over conditions）。

### 3.5 轨道 D — L2 scripted（非 AI adaptive，并列）

- `retry_full`、`path_indist` 等：**协议 / 白盒** 攻击，见 `RETRY_V2_FIXES.md`。  
- 与 L3 **分表**；用于说明 BioHarness **retry 通道**与 **文本 adaptive** 是正交威胁。

---

## 4. 统一报告表（建议附录）

**Table Adaptive-1（Live，Defense Security = 1−ASR）**

| Track | Attack | none | spotlight | bio_04 | n |
|-------|--------|------|-----------|--------|---|
| A0 | AgentDojo static | … | … | … | stress-18 |
| A1 | AutoDojo cache | … | … | … | slice |
| B0 | InjecAgent static | … | — | … | 100 |
| B2 | InjecAgent adaptive | … | — | … | 100 |
| C | AGENTVIGIL / IterInject | … | … | … | TBD |

**Table Adaptive-2（成本）**：optimizer/MCTS calls、USD（OpenRouter 汇总）。

---

## 5. 实施顺序与工时（单人）

| 顺序 | 任务 | 工时 | 依赖 |
|------|------|------|------|
| 1 | 修正 L3 report 聚合（主文口径 Security） | 0.5d | 已有 logs |
| 2 | InjecAgent 100 子集 + bio_04 static | 1–2d | 已有 live runner |
| 3 | Submodule AdaptiveAttackAgent → bio_04 | 3–5d | API |
| 4 | AutoDojo stress 子集（非仅 banking×2） | 2–3d | A1 |
| 5 | AGENTVIGIL smoke（可选） | 5–7d | GPU/时间 |

---

## 6. 脚本入口（规划）

```bash
# 已有
./scripts/supplement.sh eval/supplement/run_p1_autodojo_adaptive.py --execute
./scripts/supplement.sh eval/supplement/run_p1_injecagent_live.py --execute --max-cases 100 --defense bio_04

# 待建
# eval/supplement/run_p1_zhan_adaptive_injecagent.py  # AdaptiveAttackAgent wrapper
# eval/supplement/run_p1_agentvigil_smoke.py         # optional
```

---

## 7. 写作话术（通俗）

- **Static**：攻击者话术固定，看「默认恶意邮件/工具返回」能不能骗过 agent。  
- **Adaptive（文献）**：攻击者根据 **上一轮是否成功** 或 **MCTS/optimizer** 改话术；Zhan 2025 还强调 **针对每种 defense 专门造串**。  
- **Retry（本仓库 L2）**：不是 LLM 变聪明，而是 **利用系统「失败后重试」** 把恶意路由藏进 plan/review。  

BioHarness 要在 **三条线** 上都说清楚：Live static 已强；L3 小切片上 adaptive 文本未打穿；L2 retry 在 full bio_04 上已补洞（见 retry 文档）。
