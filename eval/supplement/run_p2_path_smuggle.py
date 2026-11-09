#!/usr/bin/env python3
"""P2: Path-smuggle + held-out subtle pollution suite (scripted harness)."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.attacks.idea1_subtle_pollution import write_dataset as write_in_dist
from eval.attacks.idea1_subtle_pollution_heldout import write_dataset as write_heldout
from eval.scripted_runner import run_scripted
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "path_smuggle_v1"
DEFAULT_CONFIG = "idea1_provenance_mlp_bio_04"


def read_jsonl(path: Path) -> list[dict]:
    import json

    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def summarize(records: list[dict]) -> dict:
    attacks = [r for r in records if r.get("label") == "attack"]
    benign = [r for r in records if r.get("label") == "benign"]
    by_type: dict[str, dict] = {}
    for r in attacks:
        t = r.get("attack_type", "unknown")
        by_type.setdefault(t, {"n": 0, "blocked": 0})
        by_type[t]["n"] += 1
        by_type[t]["blocked"] += int(r.get("blocked", False))
    return {
        "n_total": len(records),
        "n_attack": len(attacks),
        "n_benign": len(benign),
        "attack_block_rate": round(sum(int(r["blocked"]) for r in attacks) / max(len(attacks), 1), 4),
        "benign_fpr": round(sum(int(r["blocked"]) for r in benign) / max(len(benign), 1), 4),
        "by_attack_type": {
            k: {**v, "block_rate": round(v["blocked"] / max(v["n"], 1), 4)} for k, v in sorted(by_type.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P2 path-smuggle scripted suite")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--include-indist", action="store_true")
    parser.add_argument("--benign-limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    write_heldout()
    held = read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution_heldout.jsonl")
    samples = list(held)
    if args.include_indist:
        write_in_dist()
        samples += read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution.jsonl")
    if args.benign_limit:
        benign_path = ROOT / "data/benign/agent_tasks.jsonl"
        if benign_path.exists():
            for b in read_jsonl(benign_path)[: args.benign_limit]:
                b = dict(b)
                b.setdefault("label", "benign")
                samples.append(b)

    if args.dry_run:
        print(f"Would run {len(samples)} samples with config={args.config}")
        return

    runner = build_runner(args.config)
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
            }
        )

    store = SupplementRunStore(args.out_root)
    report = {"config": args.config, "summary": summarize(records), "records": records}
    store.write_json("p2", EXPERIMENT_ID, "report.json", report)

    csv_path = store.experiment_dir("p2", EXPERIMENT_ID) / "records.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    s = report["summary"]
    print(f"P2 path_smuggle → {store.experiment_dir('p2', EXPERIMENT_ID)}")
    print(f"block_rate={s['attack_block_rate']*100:.1f}% benign_fpr={s['benign_fpr']*100:.1f}%")


if __name__ == "__main__":
    main()
