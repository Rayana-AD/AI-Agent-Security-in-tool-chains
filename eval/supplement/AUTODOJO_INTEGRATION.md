# AutoDojo integration (P1 L3)

Vendor copy: `third_party/AutoDojo/` (cloned 2026-09-27)

## Goal

Register BioHarness `bio_04` as a defense in AutoDojo's adaptive optimizer and run smoke:

- 3 stress conditions × 3 defenses × B=3 iterations ≈ 27 episodes (see `runs/supplement/p1/adaptive_protocol_v1/smoke/plan.json`)

## Steps

1. **Pin commit** in `runs/supplement/manifest.json` (`third_party/AutoDojo/.git/HEAD`).
2. **Plugin** `eval/supplement/autodojo_plugin.py` (via `AGENTDOJO_DEFENSE_PLUGINS`):
   - Registers `bio_04` → `BioHarnessToolGuard(idea1_provenance_mlp_bio_04)` on tool outputs.
   - Registers `task_shield` → `TaskShieldDefense`.
3. **Verify registration**:
   ```bash
   python eval/supplement/run_p1_autodojo_smoke.py --verify-only
   ```
4. **Live smoke** (needs `OPENROUTER_API_KEY` or DeepSeek env):
   ```bash
   python eval/supplement/run_p1_autodojo_smoke.py --execute --defense bio_04
   ```
5. **Adaptive L3 (reasonable scale)**:
   ```bash
   ./scripts/supplement.sh eval/supplement/run_p1_autodojo_adaptive.py --dry-run
   ./scripts/supplement.sh eval/supplement/run_p1_autodojo_adaptive.py --execute
   ```
   Default: `banking` · 1 injection · 2 user tasks · 3 iterations · defenses `{no_defense, bio_04}`.
6. Results → `runs/supplement/p1/adaptive_l3_v1/report.json` (+ `variants/`, `benchmark_logs/`).

Pinned commit: `89413642ea43f33a98b54c5550b76b97621506dc` (2026-09-27).

## Parallel track (no AutoDojo dependency)

`eval/supplement/run_p1_adaptive_l2.py` — white-box mutations on held-out scripted samples → `runs/supplement/p1/adaptive_l2_v1/`.

## References

- Paper: Ma et al., arXiv:2606.15057 (`ma2026autodojo`)
- Repo: https://github.com/xhOwenMa/AutoDojo
