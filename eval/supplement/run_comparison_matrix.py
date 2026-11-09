#!/usr/bin/env python3
"""Run supplement attack suites across multiple harness configs (method comparison)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.attacks.idea1_subtle_pollution import write_dataset as write_in_dist
from eval.attacks.idea1_subtle_pollution_heldout import write_dataset as write_heldout
from eval.attacks.retry_abuse import generate_retry_abuse
from eval.loaders.mhj import load_mhj_subset
from eval.scripted_runner import run_scripted
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "comparison_matrix_v1"

DEFAULT_CONFIGS = [
    "idea1_provenance_mlp_bio_04",
    "bio_04_no_hard_rules",
    "idea1_provenance_mlp",
    "idea1_provenance_mlp_reflection",
    "idea1_only",
    "schema_only",
]

SUITES = ("path_heldout", "path_indist", "atomic_retry", "mhj_temporal")


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
    rows = read_jsonl(path)[:limit]
    for b in rows:
        b = dict(b)
        b.setdefault("label", "benign")
        b.setdefault("attack_type", "benign")
    return rows


def load_suite(name: str, *, benign_limit: int = 10) -> list[dict]:
    if name == "path_heldout":
        write_heldout()
        return read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution_heldout.jsonl") + load_benign(benign_limit)
    if name == "path_indist":
        write_in_dist()
        return read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution.jsonl") + load_benign(benign_limit)
    if name == "atomic_retry":
        samples = generate_retry_abuse(12)
        proc = ROOT / "data/attacks/reflection_process_samples.jsonl"
        if proc.exists():
            samples += read_jsonl(proc)
        return samples
    if name == "mhj_temporal":
        return load_mhj_subset(max_conversations=10)
    raise ValueError(name)


def summarize(records: list[dict]) -> dict:
    attacks = [r for r in records if r.get("label", "attack") != "benign"]
    benign = [r for r in records if r.get("label") == "benign"]
    by_type: dict[str, dict] = {}
    by_layer: dict[str, int] = {}
    for r in attacks:
        t = r.get("attack_type", "unknown")
        by_type.setdefault(t, {"n": 0, "blocked": 0})
        by_type[t]["n"] += 1
        by_type[t]["blocked"] += int(r.get("blocked", False))
        if r.get("blocked") and r.get("block_layer"):
            by_layer[r["block_layer"]] = by_layer.get(r["block_layer"], 0) + 1
    return {
        "n_total": len(records),
        "n_attack": len(attacks),
        "n_benign": len(benign),
        "attack_block_rate": round(sum(int(r["blocked"]) for r in attacks) / max(len(attacks), 1), 4),
        "benign_fpr": round(sum(int(r["blocked"]) for r in benign) / max(len(benign), 1), 4),
        "by_attack_type": {
            k: {**v, "block_rate": round(v["blocked"] / max(v["n"], 1), 4)}
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
    parser = argparse.ArgumentParser(description="Supplement comparison matrix")
    parser.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS)
    parser.add_argument("--suites", nargs="+", default=list(SUITES))
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    store = SupplementRunStore(args.out_root)
    matrix: dict[str, dict] = {"configs": args.configs, "suites": args.suites, "cells": {}}

    for suite in args.suites:
        samples = load_suite(suite)
        matrix["cells"][suite] = {}
        for config in args.configs:
            print(f"Running {suite} / {config} ({len(samples)} samples)...", flush=True)
            try:
                cell = run_cell(config, suite, samples)
            except KeyError as e:
                print(f"  skip {config}: {e}", flush=True)
                continue
            matrix["cells"][suite][config] = cell["summary"]
            store.write_json("p2", EXPERIMENT_ID, f"cells/{suite}/{config}.json", cell)

    store.write_json("p2", EXPERIMENT_ID, "matrix_summary.json", matrix)
    print(f"\nMatrix → {store.experiment_dir('p2', EXPERIMENT_ID)}")


if __name__ == "__main__":
    main()
