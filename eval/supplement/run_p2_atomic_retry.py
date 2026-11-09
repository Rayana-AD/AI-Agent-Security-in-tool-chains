#!/usr/bin/env python3
"""P2: Atomic split + retry_abuse scripted suites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.attacks.retry_abuse import generate_retry_abuse
from eval.scripted_runner import run_scripted
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "atomic_retry_v1"
DEFAULT_CONFIG = "idea1_provenance_mlp_bio_04"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="P2 atomic + retry abuse suite")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--retry-count", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    retry_path = ROOT / "data/attacks/retry_abuse.jsonl"
    retry_path.parent.mkdir(parents=True, exist_ok=True)
    samples = generate_retry_abuse(args.retry_count)
    with retry_path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Reflection / process samples if present
    proc_path = ROOT / "data/attacks/reflection_process_samples.jsonl"
    if proc_path.exists():
        samples += read_jsonl(proc_path)

    if args.dry_run:
        print(f"Would run {len(samples)} samples (retry_abuse + optional reflection)")
        return

    runner = build_runner(args.config)
    records = []
    for sample in samples:
        hr = run_scripted(runner, sample)
        records.append(
            {
                "sample_id": sample.get("id"),
                "attack_type": sample.get("attack_type"),
                "label": sample.get("label", "attack"),
                "blocked": hr.blocked,
                "block_layer": getattr(hr, "block_layer", ""),
                "harmful": hr.harmful,
            }
        )

    store = SupplementRunStore(args.out_root)
    attacks = [r for r in records if r["label"] != "benign"]
    store.write_json(
        "p2",
        EXPERIMENT_ID,
        "report.json",
        {
            "config": args.config,
            "n": len(records),
            "block_rate": round(sum(int(r["blocked"]) for r in attacks) / max(len(attacks), 1), 4),
            "records": records,
        },
    )
    print(f"P2 atomic_retry → {store.experiment_dir('p2', EXPERIMENT_ID)}")


if __name__ == "__main__":
    main()
