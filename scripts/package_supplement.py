#!/usr/bin/env python3
"""Build anonymous Code & Data supplement archive (method reproduction focus)."""

from __future__ import annotations

import os
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PARENT = Path.home() / "Desktop"
OUT_NAME = "BioHarness_supplement"
MAX_MB = 50

ALLOW_DIRS = [
    "src/bio_harness",
    "eval",
    "tests",
    "data",
    "models",
    "configs",
    "scripts",
]

ALLOW_FILES = [
    "pyproject.toml",
    ".gitignore",
]

# Method-reproduction scripts only (no paper figure generators)
SCRIPT_ALLOW = {
    "run_m1_manifest_seed.sh",
    "run_m1_manifest_seed_llama70.sh",
    "run_stress_manifest.sh",
    "run_bio04_reviewer_ablations.sh",
    "run_bio04_live_dropone.sh",
    "run_bio04_ceiling_ablation.sh",
    "run_ablations.sh",
    "run_m1_gated_rerun.py",
}

CONFIG_ALLOW = {
    "ablations.yaml",
    "paper_experiments.yaml",
    "paper_main_historical.yaml",
    "paper_curated.yaml",
    "stress_manifest_seed.yaml",
    "agentdojo.yaml",
    "model.yaml",
    "pilot_mhj.yaml",  # required by get_harness_config()
    "secrets.yaml.example",
}

# Eval scripts needed for method reproduction + pytest; exclude paper-plot / log-path utilities.
EVAL_EXCLUDE = {
    "plot_paper_results.py",
    "plot_paper_figures.py",
    "plot_m1_manifest_seed.py",
    "plot_results.py",
    "plot_staged_utility_recovery_compare.py",
    "plot_staged_utility_recovery_v2.py",
    "agentdojo_case_study.py",
    "train_provenance_tagger.py",
    "diagnose_utility_failures.py",
    "run_supplementary_benchmarks.py",
    "analyze_injection_depth.py",
    "run_mechanism_report.py",
    "run_experiments.py",
    "run_citation_harness.py",
    "citation_scripted_runner.py",
}

EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".git",
    ".venv",
    "runs",
    "figures",
    "logs",
    "scholarship_brief_web",
    "scholarship_brief_web_v2",
    "scholarship_brief_web_v3",
}

EXCLUDE_FILE_PATTERNS = [
    re.compile(r"secrets\.yaml$"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.DS_Store$"),
    re.compile(r"\.log$"),
    re.compile(r"main\.tex$"),
    re.compile(r"references\.bib$"),
    re.compile(r"paper_.*\.tex$"),
    re.compile(r"make_protocol_case"),
    re.compile(r"plot_paper"),
    re.compile(r"benchmark_daemon"),
    re.compile(r"monitor_benchmark"),
    re.compile(r"start_benchmark"),
    re.compile(r"benchmark_watchdog"),
    re.compile(r"3cursor_"),
    re.compile(r"scholarship"),
]

SANITIZE_PATTERNS = [
    (re.compile(r"/Users/rayana/Desktop/AI-Safety"), "."),
    (re.compile(r"/Users/rayana/Desktop/AI-Illusion[^\s\"']*"), "${LOCAL_MODEL_PATH}"),
    (re.compile(r"https://github\.com/AI-Safety"), "https://example.invalid"),
    (re.compile(r"AI-Illusion"), "local-model"),
]

FINGERPRINT_PATTERNS = [
    (re.compile(r"AI-Illusion"), "local-model fingerprint"),
    (re.compile(r"CosmosWebEnv"), "project fingerprint"),
    (re.compile(r"Wu literature"), "project fingerprint"),
    (re.compile(r"sky-map"), "project fingerprint"),
    (re.compile(r"bib_strict_verification"), "project fingerprint"),
    (re.compile(r"/Users/rayana"), "absolute user path"),
    (re.compile(r"rayana@"), "email"),
    (re.compile(r"github\.com/(?!kaijiezhu11/MELON)"), "github link"),
]

SECRET_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"/Users/rayana"),
    re.compile(r"rayana@"),
]

README = """# BioHarness — Code & Data Supplement (Method Reproduction)

Anonymous supplement for reviewer assessment. This archive contains **method
implementation, configs, offline tests, and small attack fixtures** — not paper
figures, LaTeX sources, or precomputed result tables.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,agentdojo]"
```

Optional live AgentDojo runs require API keys:

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
# fill deepseek_api_key / openrouter_api_key / huggingface_api_key
```

## Historical vs optimized configuration

| Profile | Config key | `use_carry_sens_ceiling` | Purpose |
|---------|------------|--------------------------|---------|
| **Historical main-table** | `bio_04_main_historical` in `configs/paper_main_historical.yaml` | `true` (Γ = 1.0/0.85/0.70/0.0) | Matches paper AgentDojo main runs |
| **Optimized default** | `idea1_provenance_mlp_bio_04` in `configs/ablations.yaml` | `false` (code default) | Current codebase; Γ ablation showed negligible U/S impact |

The paper Method section describes Fold–Gate–Cleave + Continuity + episode store.
Optional Sens>Γ is an engineering write-budget schedule, not the scientific claim.

Configs included: defense profiles (`ablations.yaml`, `paper_experiments.yaml`,
`paper_main_historical.yaml`), live benchmark slice (`paper_curated.yaml`,
`stress_manifest_seed.yaml`), AgentDojo wiring (`agentdojo.yaml`), model runtime
(`model.yaml`), and harness defaults (`pilot_mhj.yaml`).

## Paper Method ↔ Code mapping

| Method (paper §) | Implementation | Key files |
|------------------|----------------|-----------|
| **Fold: canonical organization** | Schema fold + semantic chunker | `src/bio_harness/fold/`, `use_schema_fold` |
| **Fold: shuffle coherence (live)** | Feature-attribution reorder | `src/bio_harness/provenance/feature_shuffle.py` |
| **Fold: shuffle coherence (scripted)** | Text reordering regression | `eval/scripted_runner.py`, `data/attacks/` |
| **Fold: Reflective Fold** | Reflection probe (d=64) | `src/bio_harness/provenance/reflection_probe.py` |
| **Fold: provenance tagging** | MLP tagger + handoff tags | `src/bio_harness/provenance/tagger.py`, `models/provenance_tagger_v2_mlp.json` |
| **Gate: direction (inbound/outbound)** | Channel gradient | `src/bio_harness/gate/channel_gradient.py` |
| **Gate: Fold handoff tag** | Gate tag + block policy | `src/bio_harness/provenance/accumulator.py`, `pipeline_check.py` |
| **Gate: Continuity soften** | Lexical overlap θ=0.08 | `src/bio_harness/provenance/reflection_probe.py` (`GOAL_CONTINUITY_OVERLAP`) |
| **Cleave: graded scopes** | none/transit/metadata/strict | `src/bio_harness/cleave/scopes.py`, `cleave_policy.py` |
| **Cleave: AgentDojo metadata strip** | IPI envelope removal | `src/bio_harness/cleave/agentdojo_ipi.py` |
| **Episode store (carry)** | Residual levels + shared flags | `src/bio_harness/provenance/carry_store.py`, `accumulator.py` |
| **Orchestration Fold→Gate→Cleave** | Continuity profile | `src/bio_harness/harness/continuity.py` |
| **Optional write budget Γ** | Sens>Γ (off by default now) | `src/bio_harness/provenance/tool_sensitivity.py` |

## Offline verification (no API keys)

```bash
pytest -q
python eval/run_bio04_config_audit.py
python eval/run_provenance_generalization_audit.py
python eval/run_provenance_integration_ablation.py
python eval/run_agentdojo_utility_bounds_audit.py
```

Expected: all unit tests pass; utility-bounds audit reproduces staged repair logic
(controlled workspace replay, not population AgentDojo rates).

## Live reproduction (reviewer API keys required)

Smoke (single batch):

```bash
./scripts/run_m1_manifest_seed.sh 1 1
```

Full main track (hours, API cost):

```bash
./scripts/run_m1_manifest_seed.sh
./scripts/run_m1_manifest_seed_llama70.sh
```

Drop-one ablations (DeepSeek, 24 conditions):

```bash
./scripts/run_bio04_live_dropone.sh
```

Optional ceiling ablation (historical Γ sensitivity):

```bash
./scripts/run_bio04_ceiling_ablation.sh m1_manifest_seed deepseek
```

Scripted attacks (offline `--no-llm` path):

```bash
./scripts/run_ablations.sh
```

## Data included

- `data/attacks/` — scripted attack JSONL (C1–C6, idea1/idea2, citation)
- `data/benign/` — benign agent tasks
- `data/agentdojo/synthetic_tasks.jsonl` — synthetic pilot tasks

AgentDojo suite environments ship with the `agentdojo` pip package; this archive
does not bundle full benchmark run logs (too large; regenerable via scripts above).

## What is intentionally excluded

- `main.tex`, `references.bib`, paper figure PDFs/PNGs
- Full `runs/` benchmark logs
- `configs/secrets.yaml` (use `secrets.yaml.example`)
- Virtual environments and caches

## Size and integrity

See `MANIFEST.sha256` for file checksums. Archive must stay under 50 MB per
conference supplement rules; no external repository links are required to obtain
this code.
"""


def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
    rel = str(path)
    for pat in EXCLUDE_FILE_PATTERNS:
        if pat.search(rel):
            return True
    return False


def copy_tree(src: Path, dst: Path) -> None:
    if src.name == "scripts":
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name in SCRIPT_ALLOW:
                shutil.copy2(item, dst / item.name)
        return
    if src.name == "configs":
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name in CONFIG_ALLOW:
                shutil.copy2(item, dst / item.name)
        return
    if src.name == "eval":
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            if should_exclude(item.relative_to(src)):
                continue
            rel = item.relative_to(src)
            if rel.parts and rel.parts[0] == "datasets":
                continue
            if item.is_file() and item.name in EVAL_EXCLUDE:
                continue
            target = dst / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        return
    if not src.is_dir():
        return
    for item in src.rglob("*"):
        if should_exclude(item.relative_to(src)):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            if should_exclude(item):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def sanitize_file(path: Path) -> None:
    if path.suffix not in {".py", ".yaml", ".yml", ".sh", ".md", ".json", ".toml"}:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    original = text
    for pattern, repl in SANITIZE_PATTERNS:
        text = pattern.sub(repl, text)
    if path.name == "model.yaml":
        text = re.sub(
            r"path:\s*\$\{LOCAL_MODEL_PATH\}",
            "path: ${LOCAL_MODEL_PATH:-Qwen/Qwen3-1.7B}",
            text,
        )
    if text != original:
        path.write_text(text, encoding="utf-8")


def scan_secrets(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "MANIFEST.sha256":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "hf_" in content and re.search(r"hf_[A-Za-z0-9]{30,}", content):
            hits.append(f"{path.relative_to(root)}: huggingface token")
        if re.search(r"sk-or-v1-[A-Za-z0-9]{20,}", content):
            hits.append(f"{path.relative_to(root)}: openrouter key")
        if re.search(r"sk-[A-Za-z0-9]{30,}", content):
            hits.append(f"{path.relative_to(root)}: api key")
        for pattern, label in FINGERPRINT_PATTERNS:
            if pattern.search(content):
                hits.append(f"{path.relative_to(root)}: {label}")
                break
    return hits


def dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def write_manifest(root: Path) -> None:
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rel = path.relative_to(root).as_posix()
            lines.append(f"{digest}  {rel}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_staging_caches(staging: Path) -> None:
    for name in ("__pycache__", ".pytest_cache"):
        for path in staging.rglob(name):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def verify_package(staging: Path) -> None:
    print("Running verification...")
    hits = scan_secrets(staging)
    if hits:
        raise SystemExit(f"Secret/identity scan failed:\n" + "\n".join(hits[:20]))

    size_mb = dir_size_mb(staging)
    print(f"Staging size: {size_mb:.2f} MB")
    if size_mb > MAX_MB:
        raise SystemExit(f"Package exceeds {MAX_MB} MB limit")

    venv_py = ROOT / ".venv" / "bin" / "python"
    pytest_python = str(venv_py) if venv_py.exists() else sys.executable

    # Offline tests
    env = {"PYTHONPATH": str(staging / "src")}
    result = subprocess.run(
        [pytest_python, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=staging,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit("pytest failed in staging directory")

    print("Verification passed.")
    clean_staging_caches(staging)
    write_manifest(staging)


def main() -> None:
    staging = OUT_PARENT / OUT_NAME
    zip_path = OUT_PARENT / f"{OUT_NAME}.zip"

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for name in ALLOW_DIRS:
        src = ROOT / name
        if src.exists():
            copy_tree(src, staging / name)

    for name in ALLOW_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, staging / name)

    (staging / "README.md").write_text(README, encoding="utf-8")

    for path in staging.rglob("*"):
        if path.is_file():
            sanitize_file(path)

    verify_package(staging)

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    zip_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {staging}")
    print(f"Wrote {zip_path} ({zip_mb:.2f} MB)")

    downloads_zip = Path.home() / "Downloads" / f"{OUT_NAME}.zip"
    shutil.copy2(zip_path, downloads_zip)
    print(f"Copied {downloads_zip} ({zip_mb:.2f} MB)")

    if zip_mb > MAX_MB:
        raise SystemExit(f"Zip exceeds {MAX_MB} MB")


if __name__ == "__main__":
    main()
