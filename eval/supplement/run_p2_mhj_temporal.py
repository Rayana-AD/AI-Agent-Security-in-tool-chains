#!/usr/bin/env python3
"""P2: MHJ-style temporal escalation (scripted harness, synthetic loader)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.loaders.mhj import load_mhj_subset
from eval.scripted_runner import run_scripted
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "mhj_temporal_v1"
DEFAULT_CONFIG = "idea1_provenance_mlp_bio_04"


def main() -> None:
    parser = argparse.ArgumentParser(description="P2 MHJ temporal scripted suite")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    samples = load_mhj_subset(max_conversations=args.limit)
    if args.dry_run:
        print(f"Would run {len(samples)} MHJ samples")
        return

    runner = build_runner(args.config)
    records = []
    for sample in samples:
        hr = run_scripted(runner, sample)
        records.append(
            {
                "sample_id": sample.get("id"),
                "tactic": sample.get("tactic"),
                "blocked": hr.blocked,
                "harmful": hr.harmful,
            }
        )

    store = SupplementRunStore(args.out_root)
    store.write_json("p2", EXPERIMENT_ID, "report.json", {"config": args.config, "records": records})
    print(f"P2 mhj_temporal → {store.experiment_dir('p2', EXPERIMENT_ID)}")


if __name__ == "__main__":
    main()
