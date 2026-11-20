# AI agent security in tool chains

Middleware for **indirect prompt injection (IPI)** in tool-using agents: a **Fold → Gate → Cleave** boundary stack with cross-turn episode memory. **No backbone fine-tuning.**

[中文版说明](README.zh.md)

> ### 30-second snapshot
>
> | | |
> |---|---|
> | **What it is** | Guards at **tool output → model** and **model → tool call**: sanitize or withhold suspicious inbound data; block risky outbound calls; remember contamination across turns. |
> | **Public numbers (AgentDojo)** | DeepSeek-Chat **stress-18**: security **38.0% → 100%**, task completion **67.6% → 92.6%**; **100%** security on all **24** conditions for DeepSeek and Llama-3-70B (Llama stress utility **64.6%**, capped by weaker planning). Offline structural suite (**111** attacks): full stack **100%** block rate. |
> | **How you use it** | Drop guards into your agent loop / `build_pipeline("bio_04", …)`; or verify locally via **quick start** below — **no API keys** required for the default path. |
>
> Figures match paper-facing configs in this repo; re-run scripts and trust your local `runs/**/*.json`.

---

## What you can do with this repo

1. **Wire middleware into your stack** — Sanitize inbound tool results and gate outbound tool calls before they run. Works with custom loops or AgentDojo `AgentPipeline` (**Path C** below).
2. **Regression-test the protocol without LLMs** — Offline matrix returns block rates in minutes (CI-friendly).
3. **Reproduce AgentDojo live numbers (API keys)** — Smoke one episode or a manifest slice; secrets stay in local `configs/secrets.yaml` (gitignored).

---

## Quick start (pick one)

| Time | Goal | Command |
|------|------|---------|
| **~2 min** | Sanity check | After `pip install -e ".[dev]"` → `pytest -q` |
| **~3–5 min** | Tests + one offline defense point (**first clone**) | `./scripts/github_quickstart.sh` |
| **~5 min** | Live model smoke (**needs key**) | **Path B → Smoke run** below |

You do **not** need to run every eval script on day one.

---

## Problem

Agents consume untrusted tool outputs (email, files, listings, APIs). Attacks hide instructions inside plausible data. Prompt-only guardrails break when the payload looks legitimate; naive blocking often **removes the data the user task still needs**.

## Method

Two boundaries: **inbound** (tool → model) and **outbound** (model → tools).

| Stage | Role |
|-------|------|
| **Fold** | Structure tool text; perturb field order to test attribution; lightweight risk signals before reasoning. |
| **Gate** | Reads vs writes: allow repaired observation; strict checks on high-impact outbound actions aligned with the user goal. |
| **Cleave** | Remove instruction **envelopes** while keeping task **cargo** (lists, fields) when they are separable. |

- Library: `src/bio_harness/` (`bio-harness` on pip)
- AgentDojo hooks: `eval/agentdojo/bio_harness_guard.py`, `eval/agentdojo/pipeline_factory.py`

---

## Requirements

| Goal | Python | Install | Notes |
|------|--------|---------|--------|
| Tests + offline matrix | ≥ 3.10 | `pip install -e ".[dev]"` | No API |
| AgentDojo live | ≥ 3.10 | `pip install -e ".[dev,agentdojo]"` | `configs/secrets.yaml` + vendored AgentDojo |
| Some live supplements | ≥ 3.10 | `pip install -e ".[supplement-live]"` | Extra `third_party` per script |

---

## Install

```bash
git clone https://github.com/Rayana-AD/AI-Agent-Security-in-tool-chains.git
cd AI-Agent-Security-in-tool-chains
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# pip install -e ".[dev,agentdojo]"   # only for live AgentDojo
```

For live runs only:

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
# Set deepseek_api_key or huggingface_api_key; routing in configs/model.yaml
```

---

## Path A: Offline attack matrix (no API; good second step)

```bash
python eval/supplement/run_official_matrix_v2.py
```

**Faster subset:**

```bash
python eval/supplement/run_official_matrix_v2.py \
  --suites path_heldout \
  --configs idea1_provenance_mlp_bio_04
```

**Output:** `runs/supplement/p2/official_matrix_v2/matrix_summary.json`

**Library entry:**

```python
from bio_harness.harness.graph import build_runner
runner = build_runner("idea1_provenance_mlp_bio_04")
```

---

## Path B: AgentDojo live benchmark (API)

Vendored source: `third_party/AutoDojo/agentdojo/src` — see [`eval/supplement/AUTODOJO_INTEGRATION.md`](eval/supplement/AUTODOJO_INTEGRATION.md) if missing.

### Smoke run

```bash
pip install -e ".[dev,agentdojo]"
python eval/run_agentdojo_benchmark.py --smoke \
  --model-mode deepseek \
  --defense none --defense bio_04
```

Pipeline alias **`bio_04`** → config **`idea1_provenance_mlp_bio_04`**. Report: `runs/agentdojo_upstream/benchmark_<timestamp>/report.json`.

### Stress manifest (one batch)

```bash
./scripts/run_m1_manifest_seed.sh 1 1
```

---

## Path C: Middleware on AgentDojo `AgentPipeline`

```python
from eval.agentdojo.pipeline_factory import build_pipeline, resolve_llm

llm, llm_name, provider = resolve_llm("deepseek")
pipeline = build_pipeline("bio_04", llm, llm_name, provider=provider)
```

Optional pieces: `BioHarnessToolGuard` (inbound), `BioHarnessPreToolGuard` (outbound), `BioHarnessEpisodeReset`. Tune via `configs/ablations.yaml` / `configs/paper_experiments.yaml`.

---

## Defense aliases

| Pipeline `defense` | Harness config key | Use |
|--------------------|--------------------|-----|
| `bio_04` | `idea1_provenance_mlp_bio_04` | Default full stack |
| `bio_remeasure` | `idea1_provenance_mlp_bio_remeasure` | Remeasure profile |
| `bio_04_no_hard_rules` | `ablations.yaml` | Offline “w/o path rules” |
| `bio_04_main_historical` | `paper_main_historical.yaml` | Older deployment |

---

## Results snapshot (paper-facing, script-reproducible)

**AgentDojo live** (stress macro, conditions in merged progress JSON):

| Model | Defense | Stress utility / security |
|-------|---------|---------------------------|
| DeepSeek-Chat | None | 67.6% / 38.0% |
| DeepSeek-Chat | BioHarness | **92.6% / 100%** |
| Llama-3-70B | None | 47.9% / 39.6% |
| Llama-3-70B | BioHarness | **64.6% / 100%** |

**Offline matrix** (111 discriminating attacks): full BioHarness **100%** block on five non-envelope suites; schema-only **~20–67%** depending on suite.

**AgentVigil banking (9 goals):** MCTS breaks **3/9** metadata-exfil goals on undefended agent; same payloads **blocked** under BioHarness (user-task checks may fail on bill-payment geometry when poison is inline).

Re-run manifests / matrix locally; your `runs/` JSON is ground truth.

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

See root `LICENSE`. Third-party benchmarks keep their own licenses.