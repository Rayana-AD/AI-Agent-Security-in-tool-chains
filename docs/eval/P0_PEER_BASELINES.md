# P0：Task Shield 与 MELON 对照（介绍、引用、数据、子集稳健性）

## 1. Task Shield 是什么

**全称**：*The Task Shield: Enforcing Task Alignment to Defend Against Indirect Prompt Injection in LLM Agents*

**作者 / 出处**：Jia, Wu, Qin & Squicciarini — **ACL 2025** (Volume 1: Long Papers), pp. 29680–29697.

**BibTeX key**：`jia2025taskshield`（见 `references.bib`）

**核心机制**（论文）：
- 在 agent **提出 tool call 时**做 **test-time goal alignment** 检查（ContributesTo / 是否服务于用户任务）。
- 与 BioHarness 的 **Continuity + Gate** 类似，属于「按目标授权动作」，但 **不做 envelope 剥离或 inbound cargo repair**。
- 依赖 backbone LLM 作 judge；misaligned 时阻断并反馈 rethink。

**本仓库实现**：`eval/agentdojo/peer_defenses.py` → `TaskShieldDefense`

**Faithful 程度（必须在论文中声明）**：
- Jia et al. **未发布官方代码**（截至本仓库接入时）。
- 实现为 **operationalization**：对每个 proposed tool call，用 **与 agent 相同的 DeepSeek-Chat** 打 `[0,1]` alignment score；`score > 0` 放行，全拦则注入 *Misalignment Detected* 反馈。
- 与论文一致的点：test-time、per-tool-call、goal 对比、阻断 + critic loop。
- 与论文可能不同的点：prompt 模板未逐字复现；parse 失败时 **fail-open**（score=1.0）。

---

## 2. MELON 是什么

**全称**：*MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Agents*

**作者 / 出处**：Zhu, Yang, Wang, Guo & Wang — **ICML 2025** (PMLR v267), pp. 80310–80329.

**官方代码**：https://github.com/kaijiezhu11/MELON

**BibTeX key**：`zhu2025melon`

**核心机制**（论文 + 官方 repo）：
- **M**asked re-**E**xecution and **TOOL** comparis**ON**
- 观察：攻击成功时，下一步 tool call **更少依赖 user task、更多依赖 malicious task**。
- 做法：在真实对话上跑一步 → 再在 **masked user prompt** 的对比轨迹上跑一步 → 比较两次 **tool call  embedding 相似度**；超过阈值则判 injection 并 **redact tool output、停止执行**。

**本仓库实现**：`eval/agentdojo/peer_defenses.py` → `MelonDefense`（自官方 `PromptInjectionDetector` / `MELON` 类移植）

**Faithful 程度（必须在论文中声明）**：
- 检测逻辑与 masking 对话模板 **follow 官方 repo**。
- **Embedding 差异**：官方用 OpenAI `text-embedding-3-large`；本仓库为避免 API 与 `eval.datasets` 包名冲突，改用 **sklearn HashingVectorizer**（512-d, ngram 1–3）。**数值不可与论文表直接对比**，只能作 **同 manifest 相对排序**。
- 默认相似度阈值 **0.8**（与官方常见设置一致）。
- 每步 tool 事件需 **额外 LLM forward**（masked path），成本约为 bio_04 的 **2×+**。

---

## 3. 评测子集与协议（是否与主表 robust）

| 维度 | 设定 | Robust? |
|------|------|---------|
| **Manifest** | 与主表相同：**24 conditions** = 4 framings × 2 injection tasks × 3 suites | ✅ 同条件可比 |
| **Model** | **DeepSeek-Chat (V3)** only（peer 跑数时） | ⚠️ 仅单 backbone；Llama peer **未跑** |
| **Agent 栈** | AgentDojo upstream pipeline + 各 defense 插件 | ✅ 与 none/spotlight/detector/bio_04 同栈 |
| **Stress 子集** | 18/24 conditions（ASR_none ≥ 10%） | ✅ 与主表 stress macro 定义一致 |
| **Episode 权重** | banking 6 ep/cond, slack 2, workspace 1 | ⚠️ workspace n=1/cond，macro 方差大 |
| **Key overlap** | peer `peer_metrics` 与 main `gate_results` **24/24 key 对齐** | ✅ |

**结论**：在 **「同 24 条件、同 DeepSeek、同 AgentDojo 协议」** 意义下，peer 对照 **robust**；但 (1) TS/MELON 为 port 非官方二进制复现；(2) 仅 DeepSeek；(3) subgroup（如 direct framing）仍 **n=2** conditions，不宜写「证明性」结论。

---

## 4. 已有 DeepSeek 数字（2026-07-12/13 跑数）

来源：`runs/paper_peer_baselines_deepseek_progress.json` + `runs/paper_m1_manifest_seed_bio_elastic_progress.json`

### 4.1 Condition-macro（24 conditions）

| Defense | Utility | Security |
|---------|---------|----------|
| none | 75.7% | 53.5% |
| Spotlighting | 75.7% | 61.1% |
| DeBERTa detector | 31.5% | 75.9% |
| **bio_04** | **94.4%** | **98.6%** |
| **task_shield** | **94.4%** | **98.6%** |
| **melon** | **66.0%** | **89.6%** |

### 4.2 Stress-macro（18 conditions，主表 primary estimand）

| Defense | Utility | Security |
|---------|---------|----------|
| none | 67.6% | 38.0% |
| **bio_04** | **92.6%** | **98.1%** |
| **task_shield** | **92.6%** | **98.1%** |
| **melon** | **65.7%** | **91.7%** |

### 4.3 Stress 按 suite 拆分

| Suite | n cond | none U/S | bio_04 U/S | task_shield U/S | melon U/S |
|-------|--------|----------|------------|-----------------|-----------|
| banking | 8 | 83.3 / 60.4 | 83.3 / 95.8 | 83.3 / 95.8 | 60.4 / 100.0 |
| slack | 6 | 91.7 / 33.3 | 100 / 100 | 100 / 100 | 100 / 75.0 |
| workspace | 4 | 0 / 0 | 100 / 100 | 100 / 100 | 25 / 100 |

**解读要点（写 Discussion / Appendix）**：
- **bio_04 ≈ task_shield** 在 macro stress 上几乎重合：二者都 **大幅优于 none**；差异在 **机制**（repair+transport vs LLM goal-check），不是 stress macro 上的大 gap。
- **MELON utility 明显低于 bio/TS**（尤其 banking 60%、workspace 25%）：符合其 **redact-and-stop** 策略，不做 cargo repair。
- **MELON banking security 100%** 但 utility 牺牲大；workspace security 100% 但 utility 25%（大量误拦/停执行）。
- **不宜声称** bio_04 显著优于 task_shield on this manifest — 应强调 **inbound repair、无额外 judge LLM、envelope cleave** 等 **正交优势**。

---

## 5. 导出与复现

```bash
# 从已有 progress JSON 生成附录表 + runs/supplement/p0/
python eval/supplement/run_p0_peer_table.py

# 若需重跑 peer（勿重复 none/spotlight/bio 已有 batch）
# 见 configs/supplement_manifest.yaml → p0_peer_rerun
python eval/run_agentdojo_benchmark.py --help
```

---

## 6. 论文附录建议段落（英文草稿）

> **Peer defenses (Appendix).** We evaluate two recent system-level baselines on the **same 24-condition DeepSeek-Chat AgentDojo manifest** as Table 1: **Task Shield** \citep{jia2025taskshield} and **MELON** \citep{zhu2025melon}. Task Shield has no public code release; we operationalize its test-time goal-alignment check with the same backbone LLM as the agent. MELON follows the public ICML implementation, except we substitute a local hashing embedder for OpenAI embeddings to avoid API coupling. Under stress-conditioned macros, Task Shield matches BioHarness (92.6\%/98.1\% utility/security), while MELON trades utility for blocking (65.7\%/91.7\%). These ports are intended for **relative ranking on a fixed manifest**, not for reproducing published absolute scores.
