# Paper remeasure scope (probe v2, minimal API)

Aligns **live BioHarness numbers** with current code (excess-shift + conjunctive reflection gate) while **keeping all non–bio_04 baselines frozen**.

Live remeasure uses defense label **`bio_05`** (same harness as `idea1_provenance_mlp_bio_04` / paper `bio_04`) so logs never overwrite July `bio_04` runs. Merge copies `bio_05` → `bio_04` in `gate_results` for Table 1 / Fig 2–3.

**Invalidated Oct 16 run:** First `bio_05` remeasure (~36% stress U) is **not** a reflection-formula regression. Causes: (1) `BioHarnessToolGuard` read raw `agentdojo_ipi_output_mode=withhold` instead of `resolve_continuity()` → envelope hits **full withhold**, never Cleave (July logs used metadata_strip + repair); (2) DeepSeek + Llama **parallel** on one `logdir` → `benchmark_*` mtime race (e.g. slack batch `report.json` shows Llama while logs are DeepSeek). Re-run **sequentially** after guard fix; use separate `probe_v2/deepseek` and `probe_v2/llama70` logdirs.

## Artifact matrix

| Artifact | Rerun? | Source |
|----------|--------|--------|
| **Fig 1** (`fig:protocol-case`) | No | Static pipeline figure |
| **Fig 2** frontier (`fig:end-to-end-frontier`) | **Partial** | Recompute from merged progress; **only bio_04** live refresh; peers unchanged |
| **Table 1** (`tab:main-results-revised`) | **Partial** | Same merge: bio_04 from probe v2; none/spot/detector from `paper_m1_manifest_seed_bio_elastic_progress.json`; TS/MELON from `paper_peer_baselines_deepseek_progress.json` |
| **Table 2** suite breakdown (`tab:suite-peer`) | **No separate run** | Re-aggregate from merged `gate_results` (same 24 keys as Table 1) |
| **Fig 3** attack framing (`fig:attack-type-tradeoff`) | **No separate run** | Same merged DeepSeek (+ existing Llama seed for Llama panel) |
| **Table 3** extended suites (`tab:extended-suites`) | **No** | Offline `official_matrix_v2` @ 100% bio_04 — already probe v2 + retry fixes |
| **Fig 4** extended gap (`fig:extended-gap`) | **No** | Same offline matrix |
| **16-batch / travel+workspace narrative** | **No** | `runs/paper_m1_framing_expand_progress.json` (16/16 batches, Oct 2026) + utility-sensitive live smokes |
| **Fig 5** staged recovery (`fig:utility-recovery`) | **Optional** | Controlled replay; prior run already 100% security at all stages — rerun only if harness cleave/staging logic changed materially |
| **Table 4** live drop-one (`tab:ablation`) | **Optional (DeepSeek)** | `scripts/run_paper_remeasure_bio04.sh dropone` → `paper_bio04_dropone_probe_v2_progress.json` |

## Live work (required)

| Step | Model | Episodes | ~Time | ~DeepSeek $ | ~OpenRouter $ |
|------|-------|---------:|------:|------------:|--------------:|
| `m1_manifest_seed` bio_04 only | DeepSeek | 72 | 30–45 min | 0.25–0.6 | — |
| Same | Llama-3.3-70B | 72 | 45–90 min | — | 0.5–1.2 |
| **Total main track** | | **144** | **~1–2 h** | **≤$0.6** | **≤$1.2** |

Then **merge** (does not overwrite July seeds):

```bash
./scripts/run_paper_remeasure_bio04.sh merge
# or full pipeline:
./scripts/run_paper_remeasure_bio04.sh main
```

Outputs:

- Live logs: `runs/agentdojo_upstream_probe_v2/`
- Raw bio_04 progress: `runs/paper_m1_manifest_seed_probe_v2_bio04_progress.json`, `..._llama70_bio04_progress.json`
- **Paper-facing merged**: `runs/paper_m1_manifest_seed_probe_v2_merged_deepseek.json`, `..._merged_llama70.json`

Frozen inputs (read-only):

- `runs/paper_m1_manifest_seed_bio_elastic_progress.json`
- `runs/paper_m1_manifest_seed_llama70_bio_elastic_progress.json`
- `runs/paper_peer_baselines_deepseek_progress.json`

## Optional (DeepSeek spare budget)

Live drop-one (appendix **Table 4**): 24 batches × **6** defenses ≈ **144** episodes, ~**45–90 min**, ~**$0.5–1.0**.

```bash
./scripts/run_paper_remeasure_bio04.sh dropone
```

Uses separate `runs/paper_bio04_dropone_probe_v2_progress.json` (does not touch `paper_bio04_dropone_elastic_progress.json`).

## What not to run

- Full 4-defense manifest (`none`/`spotlight`/`detector`/`bio_04`) — baselines unchanged.
- `m1_framing_expand` again — already complete unless a batch failed validation.
- Offline extended matrix — already at 100% for full bio_04 v2.

## After merge

```bash
.venv/bin/python eval/supplement/run_p0_peer_table.py \
  --main runs/paper_m1_manifest_seed_probe_v2_merged_deepseek.json \
  --experiment-id peer_deepseek_24cond_probe_v2

.venv/bin/python eval/plot_m1_manifest_seed.py \
  --progress runs/paper_m1_manifest_seed_probe_v2_merged_deepseek.json \
  --out figures/m1_manifest_seed_probe_v2
```

Update `main.tex` Table 1 bio_04 / Llama row from merged JSON; add footnote: *BioHarness live rows remeasured with reflection-scale v2 (Oct 2026); other defenses and peer ports frozen on prior AgentDojo batch.*
