#!/usr/bin/env python3
"""Run P0-P2 Idea2 experiments (Exp-C1 through Exp-C6)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import yaml
from tqdm import tqdm

from bio_harness.config import CONFIGS_DIR
from bio_harness.harness.graph import build_runner
from eval.attacks.idea2_datasets import write_all
from eval.metrics import RunRecord, compute_metrics, summary_to_dict
from eval.scripted_runner import run_scripted

IDEA2_EXPS = [
    "exp_c1_drattack",
    "exp_c2_cross_node",
    "exp_c3_tool_injection",
    "exp_c4_schema_smuggle",
    "exp_c5_subtle_deception",
    "exp_c6_escalation",
    "exp_idea2_all",
    "exp_idea2_v2_focus",
    "exp_c1_llm",
    "exp_c5_llm",
]

DATASET_FILES = {
    "c1_drattack": "c1_drattack.jsonl",
    "c2_cross_node": "c2_cross_node.jsonl",
    "c3_tool_injection": "c3_tool_injection.jsonl",
    "c4_schema_smuggle": "c4_schema_smuggle.jsonl",
    "c5_subtle_deception": "c5_subtle_deception.jsonl",
    "c6_escalation": "c6_escalation.jsonl",
}


def load_spec(name: str) -> dict:
    with (CONFIGS_DIR / "ablations.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if name not in spec.get("experiments", {}):
        raise KeyError(f"Unknown experiment: {name}")
    return spec["experiments"][name]


def _config_needs_llm(config_key: str) -> bool:
    with (CONFIGS_DIR / "ablations.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    cfg = spec.get("configs", {}).get(config_key, {})
    return bool(cfg.get("use_llm_shuffle_judge"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_samples(spec: dict) -> list[dict]:
    write_all()
    dataset = spec.get("dataset")
    if dataset == "idea2_all":
        samples: list[dict] = []
        for fname in DATASET_FILES.values():
            samples.extend(read_jsonl(ROOT / "data" / "attacks" / "idea2" / fname))
        return samples
    if dataset == "idea2_v2_focus":
        samples = []
        for key in ("c3_tool_injection", "c5_subtle_deception", "c6_escalation"):
            samples.extend(read_jsonl(ROOT / "data" / "attacks" / "idea2" / DATASET_FILES[key]))
        return samples
    if dataset in DATASET_FILES:
        return read_jsonl(ROOT / "data" / "attacks" / "idea2" / DATASET_FILES[dataset])
    raise ValueError(f"Unknown dataset: {dataset}")


def run_one(exp_name: str, use_llm: bool = False, limit: int | None = None, backend: str | None = None) -> dict:
    spec = load_spec(exp_name)
    samples = load_samples(spec)
    if limit is not None:
        samples = samples[:limit]
    configs = spec["configs"]

    run_dir = ROOT / "runs" / f"{exp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    by_attack: dict[str, dict] = {}

    # Reuse one LLM instance when configs enable shuffle LLM judge (avoid reload per config)
    shared_llm = None
    if any(_config_needs_llm(c) for c in configs) or use_llm or backend in ("openai", "huggingface"):
        from bio_harness.llm.factory import build_llm

        shared_llm = build_llm(backend=backend)

    for cfg in configs:
        runner = build_runner(cfg, llm=shared_llm)
        records: list[RunRecord] = []

        for sample in tqdm(samples, desc=f"{exp_name}/{cfg}"):
            result = runner.run(sample) if use_llm else run_scripted(runner, sample)
            records.append(
                RunRecord(
                    sample_id=sample.get("id", "?"),
                    label=sample.get("label", "attack"),
                    config=cfg,
                    blocked=result.blocked,
                    harmful=result.harmful,
                    escape_layer=result.escape_layer,
                    latency_seconds=result.latency_seconds,
                    token_prompt=result.token_prompt,
                    token_completion=result.token_completion,
                    attack_type=sample.get("attack_type", "none"),
                    fold_blocked=getattr(result, "fold_blocked", False),
                    gate_blocked=getattr(result, "gate_blocked", False),
                )
            )

        summary = summary_to_dict(compute_metrics(records, cfg))
        summaries.append(summary)

        for at in set(r.attack_type for r in records):
            sub = [r for r in records if r.attack_type == at]
            key = f"{cfg}::{at}"
            by_attack[key] = {
                "config": cfg,
                "attack_type": at,
                "n": len(sub),
                "asr": round(sum(1 for r in sub if r.harmful and not r.blocked) / len(sub), 4),
                "block_rate": round(sum(1 for r in sub if r.blocked) / len(sub), 4),
                "fold_block_rate": round(sum(1 for r in sub if r.fold_blocked) / len(sub), 4),
                "gate_block_rate": round(sum(1 for r in sub if r.gate_blocked) / len(sub), 4),
            }

        with (run_dir / f"{cfg}_results.jsonl").open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

    report = {
        "experiment": exp_name,
        "description": spec.get("description", ""),
        "dataset": spec.get("dataset"),
        "n_samples": len(samples),
        "summaries": summaries,
        "by_attack_type": by_attack,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def print_comparison_table(reports: list[dict]) -> None:
    print("\n=== Idea2 vs Schema (fold_block_rate) ===")
    for rep in reports:
        print(f"\n{rep['experiment']}: {rep['description']}")
        configs = {s["config"]: s for s in rep["summaries"]}
        for cfg in ("idea2_agentdojo", "idea2_only", "full", "schema_only", "idea1_only"):
            if cfg in configs:
                s = configs[cfg]
                print(
                    f"  {cfg:14s} ASR={s['asr']:.2%}  block={s['block_rate']:.2%}  "
                    f"fold_block={s.get('fold_block_rate', 0):.2%}  gate_block={s.get('gate_block_rate', 0):.2%}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P0-P2 Idea2 experiments")
    parser.add_argument(
        "--experiment",
        choices=IDEA2_EXPS + ["all", "p0", "p1", "p2", "llm"],
        default="all",
    )
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Max samples per experiment")
    parser.add_argument("--backend", choices=["local", "openai", "huggingface"], default=None, help="LLM backend override")
    args = parser.parse_args()

    if args.experiment == "all":
        names = IDEA2_EXPS[:-3]  # exclude aggregate + llm-only exps
    elif args.experiment == "p0":
        names = ["exp_c1_drattack", "exp_c2_cross_node"]
    elif args.experiment == "p1":
        names = ["exp_c3_tool_injection", "exp_c4_schema_smuggle"]
    elif args.experiment == "p2":
        names = ["exp_c5_subtle_deception", "exp_c6_escalation"]
    elif args.experiment == "llm":
        names = ["exp_c1_llm", "exp_c5_llm"]
    else:
        names = [args.experiment]

    reports = [run_one(n, use_llm=args.llm, limit=args.limit, backend=args.backend) for n in names]
    print_comparison_table(reports)
    print("\nFull reports written to runs/exp_c*_*")


if __name__ == "__main__":
    main()
