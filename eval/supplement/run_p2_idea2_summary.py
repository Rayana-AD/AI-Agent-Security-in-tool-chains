#!/usr/bin/env python3
"""P2: Run Idea2 supplementary datasets and store ordered summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.run_idea2_suite import DATASET_FILES, load_spec, read_jsonl, run_one
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "idea2_summary_v1"
DEFAULT_EXPERIMENTS = [
    "exp_c3_tool_injection",
    "exp_c5_subtle_deception",
    "exp_c6_escalation",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="P2 Idea2 supplementary summary")
    parser.add_argument("--experiments", nargs="*", default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    if args.dry_run:
        for name in args.experiments:
            spec = load_spec(name)
            ds = spec.get("dataset", "")
            path = ROOT / "data/attacks/idea2" / DATASET_FILES.get(ds, "")
            n = len(read_jsonl(path)) if path.exists() else 0
            print(f"  {name}: dataset={ds} n≈{n}")
        return

    reports = {}
    for name in args.experiments:
        reports[name] = run_one(name, use_llm=False)

    store = SupplementRunStore(args.out_root)
    store.write_json("p2", EXPERIMENT_ID, "report.json", {"experiments": reports})
    print(f"P2 idea2_summary → {store.experiment_dir('p2', EXPERIMENT_ID)}")


if __name__ == "__main__":
    main()
