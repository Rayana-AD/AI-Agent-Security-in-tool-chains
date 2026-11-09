# AI agent security in tool chains

[中文版说明](README.md)

Middleware for **indirect prompt injection (IPI)** in tool-using agents. This repo provides a **Fold → Gate → Cleave** boundary protocol with cross-turn episode state. You can wire it into an agent loop **without** fine-tuning the backbone model.

---

## Problem

Agents consume untrusted tool outputs (email, files, listings, APIs). Attacks hide instructions inside plausible data. Prompt-only guardrails break when the payload looks legitimate; naive blocking often **removes the data the user task still needs**.

## Method

The protocol runs at two boundaries: **tool output → model** (inbound) and **model → tool call** (outbound).

| Stage | Role |
|-------|------|
| **Fold** | Normalize outputs into typed fields; shuffle field order and test attribution stability; provenance tagging and reflective probes add risk signals. |
| **Gate** | Asymmetric read vs write: inbound observation may pass after repair; high-impact outbound calls need **continuity** with the user goal. An episode store tracks prior contamination. |
| **Cleave** | Strip instruction envelopes while keeping task cargo (listings, fields, etc.) so security does not zero out utility. |

Optional **Elastic** logic deepens shuffle checks when the session looks adversarial.

- Library: `src/bio_harness/` (package name `bio-harness`)
- AgentDojo hooks: `eval/agentdojo/bio_harness_guard.py`, `eval/agentdojo/pipeline_factory.py`

---

## Requirements

| Goal | Python | Install extra | Notes |
|------|--------|---------------|--------|
| Unit tests + offline matrix | ≥ 3.10 | `pip install -e ".[dev]"` | No API keys |
| AgentDojo live benchmark | ≥ 3.10 | `pip install -e ".[dev,agentdojo]"` | `configs/secrets.yaml` + vendored AgentDojo path below |
| Some supplement live tracks | ≥ 3.10 | `pip install -e ".[supplement-live]"` | Extra `third_party` per script headers |

---

## Install

```bash
git clone https://github.com/Rayana-AD/AI-Agent-Security-in-tool-chains.git
cd AI-Agent-Security-in-tool-chains

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,agentdojo]"
```

For live runs:

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
```

Set at least one provider key in `configs/secrets.yaml` (e.g. `deepseek_api_key` or `huggingface_api_key`). Routing and fallbacks: `configs/model.yaml` (`model_mode: auto` walks `model_priority`).

---

## 5-minute check (no API)

```bash
pytest -q
```

Expect all tests to pass.

---

## Path 1: Offline attack matrix (good first step)

Scripted harness on fixed samples—no external LLM calls.

```bash
python eval/supplement/run_official_matrix_v2.py
```

Default: 7 suites × 4 configs (`schema_only`, `idea1_only`, `idea1_provenance_mlp_bio_04`, `bio_04_no_hard_rules`).

**Output:** `runs/supplement/p2/official_matrix_v2/matrix_summary.json` (per-cell JSON under `cells/`).

**Faster subset:**

```bash
python eval/supplement/run_official_matrix_v2.py \
  --suites path_heldout \
  --configs idea1_provenance_mlp_bio_04
```

**Library entry:**

```python
from bio_harness.harness.graph import build_runner

runner = build_runner("idea1_provenance_mlp_bio_04")
# Same keys as configs/ablations.yaml; see eval/scripted_runner.py
```

Optional audits: `eval/run_bio04_config_audit.py`, `eval/run_provenance_generalization_audit.py`, `eval/run_agentdojo_utility_bounds_audit.py`.

---

## Path 2: AgentDojo live benchmark

### AgentDojo source path

`eval/run_agentdojo_benchmark.py` prepends:

```text
third_party/AutoDojo/agentdojo/src
```

Use a full clone that includes `third_party/AutoDojo`, or vendor it per [`eval/supplement/AUTODOJO_INTEGRATION.md`](eval/supplement/AUTODOJO_INTEGRATION.md).

### Smoke run

With `configs/secrets.yaml` configured:

```bash
python eval/run_agentdojo_benchmark.py --smoke \
  --model-mode deepseek \
  --defense none --defense bio_04
```

- `--smoke`: `workspace`, `user_task_0`, two injection tasks.
- Full stack pipeline alias: **`bio_04`** → config key **`idea1_provenance_mlp_bio_04`**.
- Report: `runs/agentdojo_upstream/benchmark_<timestamp>/report.json`.

**Example with explicit suites and defenses:**

```bash
python eval/run_agentdojo_benchmark.py \
  --suite workspace --suite banking \
  --defense none --defense spotlighting_with_delimiting --defense bio_04 \
  --model-mode deepseek
```

### Stress manifest (one batch)

```bash
./scripts/run_m1_manifest_seed.sh 1 1
```

Defenses listed in `configs/stress_manifest_seed.yaml`. Full 24-batch runs are slow and incur API cost.

---

## Path 3: Plug into your AgentDojo pipeline

```python
from eval.agentdojo.pipeline_factory import build_pipeline, resolve_llm

llm, llm_name, provider = resolve_llm("deepseek")
pipeline = build_pipeline("bio_04", llm, llm_name, provider=provider)
```

Guard classes in `eval/agentdojo/bio_harness_guard.py`:

- `BioHarnessToolGuard` — inbound tool outputs
- `BioHarnessPreToolGuard` — outbound tool calls
- `BioHarnessEpisodeReset` — reset carry per episode

Tune behavior via YAML (`configs/ablations.yaml`, `configs/paper_experiments.yaml`), not by forking guards unless you extend the protocol.

---

## Defense aliases

| Pipeline `defense` | Harness config key | Use |
|--------------------|--------------------|-----|
| `bio_04` | `idea1_provenance_mlp_bio_04` | Default full stack |
| `bio_remeasure` | `idea1_provenance_mlp_bio_remeasure` | Remeasure / carry profile |
| `bio_04_minus_hard_rules` | same in `paper_experiments.yaml` | Ablate path hard rules |
| `bio_04_no_hard_rules` | same in `ablations.yaml` | Offline matrix “w/o path” |
| `bio_04_main_historical` | `paper_main_historical.yaml` | Older deployment (carry ceiling, etc.) |

---

## Benchmarks at a glance

Numbers depend on model and manifest—treat your `runs/**/*.json` as ground truth.

| Track | Entry | Summary |
|-------|--------|---------|
| AgentDojo multi-suite | `run_agentdojo_benchmark.py`, `run_m1_manifest_seed.sh` | Full stack targets high macro security with cargo repair vs block-only detectors. |
| Offline 7-suite matrix | `run_official_matrix_v2.py` | Schema-only fails on path/retry threats; full stack + path rules closes the gap. |
| Adaptive supplements | `eval/supplement/run_golorial_agentvigil_slice.py`, etc. | Replay search-hardened payloads; inline exfil cases trade utility for containment. |

---

## Layout

```text
src/bio_harness/
eval/agentdojo/
eval/supplement/
configs/
data/attacks/
models/
tests/
```

---

## License

See the root `LICENSE` file when present. Third-party benchmarks (AgentDojo, AutoDojo, …) keep their own licenses.
