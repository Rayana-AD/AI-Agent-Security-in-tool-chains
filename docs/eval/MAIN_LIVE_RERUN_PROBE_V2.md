# Main live AgentDojo rerun (probe v2, non-destructive)

Reproduce **Table 1 BioHarness row** (and optionally Llama) with the **current** code path:

- Excess-shift normalization (Eq. excess-shift / paper Eq. 5–6)
- Conjunctive step stress \(c_{\mathrm{step}}=\min(1,\hat\alpha,\hat\delta)\)
- Sentence-level segment calibration (`.cache/reflection_scales.json`, p90)
- bio_04 v2 harness (plan merge, path/routing hard rules where applicable)

**Does not modify** July 2026 artifacts:

| Keep frozen | New v2 paths |
|-------------|----------------|
| `runs/agentdojo_upstream/` | `runs/agentdojo_upstream_probe_v2/` |
| `runs/paper_m1_manifest_seed_bio_elastic_progress.json` | `runs/paper_m1_manifest_seed_probe_v2_*.json` |
| `runs/supplement/p0/peer_deepseek_24cond/` | `runs/supplement/p0/peer_deepseek_24cond_probe_v2/` |

Task Shield / MELON peer numbers can stay on the **old** `paper_peer_baselines_deepseek_progress.json`; only the **bio_04 / none / spotlight / detector** rows need to come from the v2 progress file when updating the paper.

---

## Scale (DeepSeek `m1_manifest_seed`)

| Item | Count |
|------|------:|
| User tasks | 9 (banking 6, slack 2, workspace 1) |
| Attack framings | 4 (+ `direct`) |
| Injection tasks | 2 |
| **Conditions** (attack × inj × suite) | **24** |
| **Batches** (one suite per batch) | **24** |
| Episodes if **4 defenses** | **288** |
| Episodes if **bio_04 only** | **72** |

Appendix **framing expand** (`m1_framing_expand`): **16 batches**, 128 episodes (4 defenses) or 32 episodes (bio_04 only).

---

## Time estimate (from prior logs ~5 min/batch @ 4 defenses)

| Mode | Batches | Wall clock (order of magnitude) |
|------|--------:|----------------------------------|
| `bio_only` (DeepSeek) | 24 | **30–45 min** |
| `full` (4 defenses) | 24 | **90–120 min** |
| `expand` | 16 | **60–80 min** (4 defenses) |
| `llama` bio_04 | 24 | **45–90 min** (OpenRouter latency) |

Your **~1 h** budget fits **DeepSeek `bio_only` + `expand` bio_04** comfortably, or **DeepSeek `full`** if batches stay fast.

---

## Cost estimate (API $)

AgentDojo episodes are short multi-turn traces (~5–15 LLM calls each). Rough order of magnitude (not a quote):

| Run | Episodes | DeepSeek ~$ | OpenRouter Llama ~$ |
|-----|--------:|------------:|--------------------:|
| DeepSeek bio_04 only | 72 | **$0.25–0.60** | — |
| DeepSeek 4 defenses | 288 | **$1.0–1.8** | — |
| + framing expand (bio_04) | +32 | **+$0.15–0.30** | — |
| Llama bio_04 only | 72 | — | **$0.5–1.2** |

With **~$2 DeepSeek + ~$1.5 OpenRouter**, a practical package is:

1. **DeepSeek `full`** (24 batches, 4 defenses) → refresh entire non-peer main table block for DeepSeek.  
2. **DeepSeek `expand`** (optional, 16 batches) → substantiate 16-batch / travel+workspace claims.  
3. **Llama `llama`** (bio_04 only) → refresh Llama BioHarness row without rerunning baselines.

If budget is tight, minimum for **method–code alignment**:

- **DeepSeek `bio_only`**, then merge bio_04 cells into July `gate_results` via `scripts/merge_bio_elastic_gate_results.py` (same pattern as the elastic remasure). Baselines none/spot/detector stay frozen; only bio_04 rows refresh.

Note: `bio_only` batches omit `none`, so `stress_ok` is not computed per batch during the run—use merged progress or run `full` once for stress flags.

---

## Commands

```bash
chmod +x scripts/run_m1_manifest_seed_probe_v2.sh

# Recommended first pass (cheap, method-aligned bio row):
./scripts/run_m1_manifest_seed_probe_v2.sh bio_only

# Paper-grade DeepSeek block (none, spotlight, detector, bio_04):
./scripts/run_m1_manifest_seed_probe_v2.sh full

# Appendix travel + workspace extras:
./scripts/run_m1_manifest_seed_probe_v2.sh expand

# Llama capacity row (bio_04 only):
./scripts/run_m1_manifest_seed_probe_v2.sh llama
```

Aggregate (example after `full`):

```bash
.venv/bin/python eval/plot_m1_manifest_seed.py \
  --progress runs/paper_m1_manifest_seed_probe_v2_progress.json \
  --out figures/m1_manifest_seed_probe_v2

.venv/bin/python eval/supplement/run_p0_peer_table.py \
  --main runs/paper_m1_manifest_seed_probe_v2_progress.json \
  --experiment-id peer_deepseek_24cond_probe_v2
```

Compare to July baseline:

```bash
.venv/bin/python eval/supplement/run_p0_peer_table.py \
  --main runs/paper_m1_manifest_seed_bio_elastic_progress.json \
  --experiment-id peer_deepseek_24cond
```

---

## Expected metric movement

- **Macro U/S**: usually **±0–2 pp**; largest swings in **direct** and **banking** cells tied to reflection/outbound gating.
- **Utility**: more often **up or flat** on travel/workspace after excess-shift (fewer false process blocks).
- **Security**: **flat or up** on envelope-heavy cells; watch **direct|banking** (historically ~83% security).

After v2 completes, update `main.tex` Table 1 from `peer_deepseek_24cond_probe_v2/report.json` and add a footnote: *Live AgentDojo macro averages reproduced October 2026 with reflection-scale v2; Task Shield/MELON peer rows from frozen March–July peer port batch.*
