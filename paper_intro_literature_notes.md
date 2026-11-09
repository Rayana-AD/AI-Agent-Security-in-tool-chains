# Intro literature: content-driven selection

## Principle
Cite only what a sentence in `paper_introduction_revised.tex` needs.
Do **not** pad with “also AgentDojo defense” papers that do not change positioning.
Author geography is not a filter; **claim fit** is. The previous expansion overweighted a cluster of concurrent AgentDojo system papers (BIPIA / MELON / DRIFT / IPIGuard) that were not baselines and were not needed for the gap statement.

## Intro narrative (three beats)

1. **Setting and threat**  
   ReAct agents → AgentDojo workloads → IPI via tool returns (Greshake) → agent benches (AgentDojo, InjecAgent) → delayed effect (Liu formalizing) → adjacent memory threat for scope (AgentPoison).

2. **Defense layers → our gap**  
   Marking (Spotlighting) · detectors (ProtectAI) · model training (Instruction Hierarchy, StruQ, SecAlign) · system/runtime (CaMeL capabilities, Task Shield goal checks) → gap: no fine-tune / no capability rewrite, yet wrappers still trade utility vs security; adaptive attacks motivate honest scope (Zhan adaptive).

3. **This work + contributions**  
   Transport / Fold–Gate–Cleave; empirical claim; three contributions (no number dump).

## Cite map (14 keys)

| Key | Supports | Why kept |
|-----|----------|----------|
| `yao2023react` | agent paradigm | setting |
| `debenedetti2024agentdojo` | eval + utility/security tradeoff | our bench + gap |
| `greshake2023indirect` | IPI definition | canonical threat |
| `zhan2024injecagent` | tool-agent IPI benches | complementary suite |
| `liu2024formalizing` | delayed / formalized PI | “not one-shot jailbreak” |
| `chen2024agentpoison` | memory poisoning | **scope boundary** (not our attack class) |
| `hines2024spotlighting` | prompt marking | **baseline** |
| `protectai2024pideetector` | detector | **baseline** |
| `wallace2024instruction` | model privilege | model-layer contrast |
| `chen2025struq` | structured queries + fine-tune | model-layer contrast (Berkeley / USENIX’25) |
| `chen2025secalign` | preference optimization | model-layer contrast (CCS’25) |
| `debenedetti2025camel` | capability policies | **scope contrast** in Abstract |
| `jia2025taskshield` | test-time task alignment | closest peer to Gate / goal continuity (ACL’25) |
| `zhan2025adaptive` | adaptive bypass | **honest scope** |

## Explicitly dropped from Intro (were list-padding)

| Key | Reason |
|-----|--------|
| `yi2025bipia` | Application-LLM BIPIA; not our agent-loop eval |
| `zhu2025melon` | Strong related AgentDojo defense, but not a baseline and not required for the gap claim |
| `li2025drift` | Same: concurrent system defense, redundant with CaMeL + Task Shield for Intro |
| `an2025ipiguard` | Same |

These can return in a Related Work subsection if you later compare mechanisms in depth—not as Intro decoration.

## Still ~2× vs original 7?
Original core was ~7. Current set is **14**, but each entry earns its slot by claim fit (including StruQ / SecAlign / Task Shield / AgentPoison replacing the BIPIA–DRIFT–IPIGuard cluster).
