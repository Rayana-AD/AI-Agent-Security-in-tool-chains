#!/usr/bin/env python3
"""Factorial experiments: separate Idea1 (channel) vs Idea2 (shuffle)."""

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
from eval.attacks.fragmented_shuffle import write_dataset as write_fragmented
from eval.attacks.retry_abuse import write_dataset as write_retry_abuse
from eval.datasets.benign_tasks import write_dataset as write_benign
from eval.loaders.liars_bench import load_liars_subset
from eval.loaders.mhj import load_mhj_subset
from eval.metrics import RunRecord, compute_metrics, summary_to_dict
from eval.scripted_runner import run_scripted


def load_experiment_spec(name: str) -> dict:
    with (CONFIGS_DIR / "ablations.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if name not in spec.get("experiments", {}):
        raise KeyError(f"Unknown experiment: {name}. Choose: {list(spec['experiments'])}")
    return spec["experiments"][name]


def load_samples_for_exp(attack_types: list[str] | None, include_benign: bool) -> list[dict]:
    write_fragmented(30)
    write_retry_abuse(30)
    write_benign(40)

    def read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    all_samples: list[dict] = []
    all_samples.extend(read_jsonl(ROOT / "data" / "attacks" / "fragmented_shuffle.jsonl"))
    all_samples.extend(read_jsonl(ROOT / "data" / "attacks" / "retry_abuse.jsonl"))
    all_samples.extend(load_mhj_subset(50, 5))
    all_samples.extend(load_liars_subset(["instructed-deception", "harm-pressure-choice"], 30))

    if include_benign:
        all_samples.extend(read_jsonl(ROOT / "data" / "benign" / "agent_tasks.jsonl"))

    if attack_types:
        filtered = [s for s in all_samples if s.get("attack_type") in attack_types]
        if include_benign:
            filtered.extend([s for s in all_samples if s.get("label") == "benign"])
        return filtered
    return all_samples


def run_experiment(exp_name: str, use_llm: bool = False) -> dict:
    spec = load_experiment_spec(exp_name)
    samples = load_samples_for_exp(spec.get("attack_types"), spec.get("include_benign", True))
    configs = spec["configs"]

    run_dir = ROOT / "runs" / f"{exp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    by_attack: dict[str, dict] = {}

    for cfg in configs:
        runner = build_runner(cfg)
        records: list[RunRecord] = []

        for sample in tqdm(samples, desc=f"{exp_name}/{cfg}"):
            if use_llm:
                result = runner.run(sample)
            else:
                result = run_scripted(runner, sample)

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

        for at in set(r.attack_type for r in records if r.label == "attack"):
            sub = [r for r in records if r.attack_type == at and r.label == "attack"]
            if not sub:
                continue
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
        "attack_types": spec.get("attack_types"),
        "n_samples": len(samples),
        "summaries": summaries,
        "by_attack_type": by_attack,
    }
    out = run_dir / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--experiment",
        choices=["exp_a_shuffle", "exp_b_channel", "factorial_2x2", "all"],
        default="all",
    )
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()

    names = (
        ["exp_a_shuffle", "exp_b_channel", "factorial_2x2"]
        if args.experiment == "all"
        else [args.experiment]
    )
    reports = [run_experiment(n, use_llm=args.llm) for n in names]
    print(json.dumps(reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
