# GitHub 红队 / IPI 评测项目调研（P1 集成参考）

调研日期：2026-09-27。用于 P1 adaptive 与 P2 baseline 扩展。

**完整对照表（任务 / 规模 / 指标 / 本仓库映射）**：见 [`OFFICIAL_ATTACK_BASELINE_SPEC.md`](OFFICIAL_ATTACK_BASELINE_SPEC.md)。

**Adaptive 多轨方案（文献对齐，非仅 AutoDojo）**：见 [`P1_ADAPTIVE_LITERATURE_PLAN.md`](P1_ADAPTIVE_LITERATURE_PLAN.md)。

**Retry v2 修复说明**：见 [`RETRY_V2_FIXES.md`](RETRY_V2_FIXES.md)。

---

## 1. 优先级 A — 建议直接集成或对照

| 项目 | URL | 类型 | 与 BioHarness 关系 | 集成状态 | 预估工时 |
|------|-----|------|-------------------|----------|----------|
| **AutoDojo** | https://github.com/xhOwenMa/AutoDojo | Adaptive black-box IPI on AgentDojo | **P1 L3 主协议**；测 static 98% 是否虚高 | 未集成；需注册 `bio_04` defense | 3–5 天 smoke；+1–2 周 full slice |
| **AgentDojo** | https://github.com/ethz-spylab/agentdojo | 基准 + defense 插件 | 已在用 upstream benchmark | ✅ 已用 | — |
| **MELON (official)** | https://github.com/kaijiezhu11/MELON | Defense | P0 peer；可 diff 本地 port | Port 在 `peer_defenses.py` | 1 天 diff 测试 |
| **IPIGuard** | https://github.com/Greysahy/ipiguard | TDG 结构约束 defense | P2 peer；EMNLP 2025 Oral | 未集成 | 4–7 天（AgentDojo adapter） |

---

## 2. 优先级 B — 攻击生成 / 原子化 / adaptive 文献实现

| 项目 | URL | 类型 | 用途 |
|------|-----|------|------|
| **Zhan et al. adaptive attacks** | 见 ACL Anthology `zhan2025adaptive`；代码常随 InjecAgent 生态 | Adaptive IPI | L1 grey-box 策略参考 |
| **InjecAgent** | https://github.com/uiuc-kang-lab/InjecAgent | Agent attack benchmark | 扩展 threat；非 AgentDojo 主表 |
| **AgentPoison** | https://github.com/safety-research/AgentPoison | Memory poisoning | P2 scope 边界（非 IPI 主表） |
| **本仓库 atomic_split** | `eval/attacks/atomic_split.py` | Within-episode fragment IPI | P2 已 scaffold；需扩跑 |

---

## 3. 优先级 C — 防御对照（定性或后续）

| 项目 | URL | 说明 |
|------|-----|------|
| **CaMeL** | https://arxiv.org/abs/2503.18813 | Capability-enforced interpreter；**无统一公开 AgentDojo 复现** → Discussion 定性 |
| **Task Shield** | ACL 2025；**无官方 code** | 已在 `peer_defenses.py` |
| **Spotlighting** | AgentDojo built-in | 主表已有 |
| **ProtectAI DeBERTa** | AgentDojo built-in | 主表已有 |
| **Progent / DRIFT** | AutoDojo 论文中列为 system-level 更稳 | 可选 P2+ peer |

---

## 4. 推荐集成顺序

```
1. eval/supplement/run_p0_peer_table.py     （已有数据 → 附录表）
2. AutoDojo submodule + bio_04 plugin       （P1 L3）
3. eval/supplement/run_p2_path_smuggle.py   （已知 0/4 弱点扩集）
4. Greysahy/ipiguard AgentDojo wrapper      （P2 peer）
5. multi-hop carry scripted suite             （P2）
6. MHJ / Idea2 supplementary runners        （P2）
```

---

## 4. BibTeX 待补（P2）

`references.bib` 建议新增：

```bibtex
@misc{an2025ipiguard,
  title   = {{IPIGuard}: A Novel Tool Dependency Graph-Based Defense Against Indirect Prompt Injection in {LLM} Agents},
  author  = {An, Hengyu and Zhang, Jinghuai and Du, Tianyu and Zhou, Chunyi and Li, Qingming and Lin, Tao and Ji, Shouling},
  year    = {2025},
  eprint  = {2508.15310},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CR},
  note    = {EMNLP 2025 Main; code: https://github.com/Greysahy/ipiguard}
}

@article{ma2026autodojo,
  title   = {{AutoDojo}: Adaptive Black-Box Attacks Reveal the Limits of {IPI} Defenses and Task-Specification Effects in {LLM} Agents},
  author  = {Ma, X. and others},
  year    = {2026},
  eprint  = {2606.15057},
  note    = {Adaptive AgentDojo extension; code: https://github.com/xhOwenMa/AutoDojo}
}
```

（作者列表以正式发表为准。）

---

## 5. 风险说明

- **AutoDojo** 与 **IPIGuard** 依赖 AgentDojo 版本；pin commit 并写进 `runs/supplement/manifest.json`。
- **IPIGuard** 是 **defense** baseline，不是 attack； adaptive 应用 **against bio_04** 需额外攻击者模块。
- 勿将 **citation hallucination** harness 与 IPI 主 ASR 混表（不同 threat model）。
