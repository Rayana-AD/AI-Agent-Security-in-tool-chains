#!/usr/bin/env python3
"""Official-spec supplement matrix v2: full-scale scripted suites + main-text baseline configs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.attacks.fragmented_shuffle import generate_fragmented
from eval.attacks.idea1_subtle_pollution import write_dataset as write_in_dist
from eval.attacks.idea1_subtle_pollution_heldout import write_dataset as write_heldout
from eval.attacks.retry_abuse import generate_retry_abuse
from eval.scripted_runner import run_scripted
from eval.supplement.results_store import SupplementRunStore
from eval.loaders.liars_bench import load_liars_subset
from eval.supplement.sample_adapters import adapt_reflection_process, build_mhj_multihop_synthetic

EXPERIMENT_ID = "official_matrix_v2"

# Main-text / ablation baselines (scripted offline proxies — see OFFICIAL_ATTACK_BASELINE_SPEC.md)
DEFAULT_CONFIGS = [
    "schema_only",
    "idea1_only",
    "idea1_provenance_mlp_bio_04",
    "bio_04_no_hard_rules",
]

SUITES = (
    "path_heldout",
    "path_indist",
    "retry_full",
    "fragmented_shuffle",
    "reflection_process",
    "mhj_multihop",
    "liars_bench",
)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_benign(limit: int = 10) -> list[dict]:
    path = ROOT / "data/benign/agent_tasks.jsonl"
    if not path.exists():
        return []
    rows = []
    for row in read_jsonl(path)[:limit]:
        row = dict(row)
        row.setdefault("label", "benign")
        row.setdefault("attack_type", "benign")
        rows.append(row)
    return rows


def load_suite(name: str, *, benign_limit: int = 10) -> list[dict]:
    if name == "path_heldout":
        write_heldout()
        return read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution_heldout.jsonl") + load_benign(benign_limit)
    if name == "path_indist":
        write_in_dist()
        return read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution.jsonl") + load_benign(benign_limit)
    if name == "retry_full":
        return generate_retry_abuse(30)
    if name == "fragmented_shuffle":
        return generate_fragmented(30)
    if name == "reflection_process":
        proc = ROOT / "data/attacks/reflection_process_samples.jsonl"
        return [adapt_reflection_process(s) for s in read_jsonl(proc)]
    if name == "mhj_multihop":
        return build_mhj_multihop_synthetic(20)
    if name == "liars_bench":
        return load_liars_subset(["instructed-deception", "harm-pressure-choice"], max_per_subset=20)
    raise ValueError(name)


def summarize(records: list[dict]) -> dict:
    attacks = [r for r in records if r.get("label", "attack") != "benign"]
    benign = [r for r in records if r.get("label") == "benign"]
    by_type: dict[str, dict] = {}
    by_layer: dict[str, int] = {}
    for r in attacks:
        t = r.get("attack_type", "unknown")
        by_type.setdefault(t, {"n": 0, "blocked": 0, "attack_success": 0})
        by_type[t]["n"] += 1
        by_type[t]["blocked"] += int(r.get("blocked", False))
        by_type[t]["attack_success"] += int(r.get("attack_success", False))
        if r.get("blocked") and r.get("block_layer"):
            by_layer[r["block_layer"]] = by_layer.get(r["block_layer"], 0) + 1
    return {
        "n_total": len(records),
        "n_attack": len(attacks),
        "n_benign": len(benign),
        "attack_block_rate": round(sum(int(r["blocked"]) for r in attacks) / max(len(attacks), 1), 4),
        "attack_success_rate": round(
            sum(int(r.get("attack_success", False)) for r in attacks) / max(len(attacks), 1), 4
        ),
        "benign_fpr": round(sum(int(r["blocked"]) for r in benign) / max(len(benign), 1), 4),
        "by_attack_type": {
            k: {
                **v,
                "block_rate": round(v["blocked"] / max(v["n"], 1), 4),
                "asr": round(v["attack_success"] / max(v["n"], 1), 4),
            }
            for k, v in sorted(by_type.items())
        },
        "block_layers": by_layer,
    }


def run_cell(config: str, suite: str, samples: list[dict]) -> dict:
    runner = build_runner(config)
    records = []
    for sample in samples:
        hr = run_scripted(runner, sample)
        records.append(
            {
                "sample_id": sample.get("id"),
                "label": sample.get("label", "attack"),
                "attack_type": sample.get("attack_type", ""),
                "blocked": hr.blocked,
                "block_layer": getattr(hr, "block_layer", ""),
                "block_reason": getattr(hr, "block_reason", ""),
                "harmful": hr.harmful,
                "attack_success": sample.get("label", "attack") != "benign" and hr.harmful and not hr.blocked,
            }
        )
    return {"config": config, "suite": suite, "summary": summarize(records), "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Official supplement matrix v2")
    parser.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS)
    parser.add_argument("--suites", nargs="+", default=list(SUITES))
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--experiment-id", default=EXPERIMENT_ID)
    args = parser.parse_args()

    store = SupplementRunStore(args.out_root)
    experiment_id = args.experiment_id
    spec_ref = "docs/eval/OFFICIAL_ATTACK_BASELINE_SPEC.md"
    matrix: dict = {
        "experiment_id": experiment_id,
        "spec_ref": spec_ref,
        "configs": args.configs,
        "suites": args.suites,
        "live_baselines_note": (
            "AgentDojo none/spotlight/detector/TS/MELON are in p0/peer_deepseek_24cond — not scripted."
        ),
        "cells": {},
        "suite_sizes": {},
    }

    for suite in args.suites:
        samples = load_suite(suite)
        matrix["suite_sizes"][suite] = {
            "n_total": len(samples),
            "n_attack": sum(1 for s in samples if s.get("label", "attack") != "benign"),
            "n_benign": sum(1 for s in samples if s.get("label") == "benign"),
        }
        matrix["cells"][suite] = {}
        for config in args.configs:
            print(f"Running {suite} / {config} ({len(samples)} samples)...", flush=True)
            try:
                cell = run_cell(config, suite, samples)
            except KeyError as e:
                print(f"  skip {config}: {e}", flush=True)
                continue
            matrix["cells"][suite][config] = cell["summary"]
            store.write_json("p2", experiment_id, f"cells/{suite}/{config}.json", cell)

    store.write_json("p2", experiment_id, "matrix_summary.json", matrix)
    print(f"\nMatrix v2 → {store.experiment_dir('p2', experiment_id)}")


if __name__ == "__main__":
    main()
