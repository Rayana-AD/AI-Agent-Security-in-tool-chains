# P0–P2 执行路线图与时间预估

| 阶段 | 交付物 | 状态 | 预估（单人） |
|------|--------|------|--------------|
| **P0** | Task Shield / MELON 介绍 + 引用 + 24cond 表 | ✅ 数据已导出 | 0.5d（写 Appendix） |
| **P1a** | Adaptive 协议 JSON + AutoDojo 集成计划 | ✅ protocol scaffold | 3–5d smoke |
| **P1b** | AutoDojo × bio_04 stress slice (B=10) | ⏳ 待接 repo | 5–8d |
| **P1c** | Threshold sensitivity 11 configs × 18 cond | ✅ grid ready | 3–4d |
| **P2a** | Path-smuggle 扩集 + 重跑 | ✅ script ready | 1d |
| **P2b** | Multi-hop carry scripted | ✅ script ready | 1–2d |
| **P2c** | Atomic / retry / MHJ / Idea2 | ✅ scripts ready | 2–3d |
| **P2d** | IPIGuard AgentDojo adapter | 📋 plan only | 4–7d |
| **P2e** | Llama peer + adaptive | ⏳ | +1–2 周 |

**合计到 rebuttal-ready**：约 **3–4 周**（DeepSeek 为主）；**全量含 IPIGuard + Llama**：**5–7 周**。

## 本周建议顺序

1. 把 `runs/supplement/p0/peer_deepseek_24cond/table.md` 贴进论文 Appendix  
2. 软化 §4.2 subgroup「100%」措辞（见 P0 doc）  
3. `run_all_supplement.py --phase p2 --execute-p2` 跑出 path/retry 弱点表  
4. Clone AutoDojo → 注册 bio_04 → P1 smoke 27 episodes  

## 命令

```bash
# 官方规格对照 + v2 矩阵（见 docs/eval/OFFICIAL_ATTACK_BASELINE_SPEC.md）
python eval/supplement/run_p0_peer_table.py
python eval/supplement/run_official_matrix_v2.py
python eval/supplement/visualize_supplement_results.py --matrix official_matrix_v2
python eval/supplement/run_p1_autodojo_smoke.py --verify-only

python eval/supplement/run_all_supplement.py --execute-p2   # P2 harness (v1 matrix)
python eval/supplement/run_all_supplement.py --phase p1     # protocol only
```
