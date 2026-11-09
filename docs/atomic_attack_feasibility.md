# Atomic / fragmented attacks vs BioHarness — feasibility notes

## What the literature means by “atomic” / fragmented attacks

Recent work splits a harmful goal into locally benign pieces that only become dangerous when composed:

| Work | Setting | Mechanism | Public code? |
|------|---------|-----------|--------------|
| **FragFuse** (2026) | Memory-augmented agents + access control | Fragment → store in long-term memory → fuse later | Project page; check arXiv |
| **FragBench** (2026) | Cross-session misuse | Multi-session benign-looking fragments | github.com/LidaSafety/fragbench |
| **CKA-Agent / Trojan Knowledge** (2025) | Guardrail jailbreaks | Benign sub-queries woven, then synthesized | arXiv |
| **Unit42 memory PoC** | Agent long-term memory | Split IPI across forged XML blocks into session summary | Blog PoC |
| **Our scripted suite** (already in repo) | Single-episode AgentDojo-like narratives | Task decomposition, cross-node fragmentation, schema smuggle | `runs/exp_c*` / Method text-reordering |

Consensus: **single-turn input filters and per-message detectors are weak** against composition across turns/sessions/memory. System defenses that track **continuity / goal contribution across steps** (Task Shield, BioHarness Gate+carry, MELON dual-trajectory) are closer to the right abstraction, but **none claim a general solution** for cross-session memory fusion.

## Can we reproduce on AgentDojo?

### A. Already partially covered (cheap — use existing artifacts)
BioHarness scripted / text-path suites already include:
- **Task decomposition**
- **Cross-node fragmentation**
- **Schema-structured smuggling**

Paper Results cite residual misses on **structured field smuggling, path smuggling, retry paraphrases**.  
**Action:** re-report those numbers as the “atomic-within-episode” stress test; optionally expand fixtures.

### B. Live AgentDojo adaptation (medium — recommended next attack track)
AgentDojo injections are **one placeholder string per tool output**. To approximate atomic IPI without a memory store:

1. **Multi-placeholder split attack** (new `BaseAttack`):
   - Split `injection_task.GOAL` into 2–4 locally benign fragments (e.g. recipient / amount / “please execute prior steps”).
   - If the user-task ground truth exposes **multiple** injection placeholders, place one fragment per placeholder.
   - If only one placeholder exists, pack fragments as separate “notes” / list items in one observation (schema smuggle style).

2. **Multi-turn delayed fuse** (harder):
   - Requires environment state that persists attacker-controlled text across tool calls (email body → later read). Banking/Slack/workspace already have such channels — craft injection tasks that **write** benign fragments then **read+fuse**.

3. **Not a drop-in for FragFuse/FragBench**:
   - Those need **long-term memory / cross-session graphs**. AgentDojo episodes are short and memory-less unless we add a memory tool. Full FragFuse reproduction is **out of scope** for the current 24-condition protocol.

### C. Suggested BioHarness evaluation plan
1. Implement `atomic_split` attack registering 3 morphologies: `split_placeholders`, `schema_list_smuggle`, `cross_tool_fuse`.
2. Run **none vs bio_04 vs task_shield vs melon** on a **small stress slice** (e.g. banking + slack, `injection_task_0/1`, DeepSeek) — not full 24×4 first.
3. Report: ASR, which Fold/Gate layer fired, and whether Cleave over-repaired utility.
4. Honest claim: tests **within-episode atomic IPI**, not FragFuse-style memory fusion.

## Relation to current peer runs
Task Shield / MELON peer baselines use the **standard** AgentDojo attack framings (important_instructions / direct / persona / education). Atomic attacks are a **separate follow-up experiment**.

## Implementation (ready)

| Artifact | Role |
|----------|------|
| `eval/attacks/atomic_split.py` | Registers `atomic_split`, `atomic_split_placeholders`, `atomic_schema_smuggle` |
| `configs/paper_curated.yaml` → `m1_atomic_slice` | banking(4)+slack(2) × 2 attacks × 2 inj × 4 defenses → **8 batches** |
| `scripts/run_atomic_slice.py` | Runner + summary |
| `scripts/run_after_peer_then_atomic.py` | Wait for peer 24/24, then launch atomic |

Defenses under atomic: `none`, `bio_04`, `task_shield`, `melon`.

```bash
# chained (preferred):
.venv/bin/python -u scripts/run_after_peer_then_atomic.py

# or manual after peer:
.venv/bin/python -u scripts/run_atomic_slice.py
```

