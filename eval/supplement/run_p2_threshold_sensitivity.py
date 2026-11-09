#!/usr/bin/env python3
"""P1/P2: Generate threshold sensitivity grid configs (does not run AgentDojo by default)."""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.protocol_adaptive import BIOHARNESS_THRESHOLDS
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "threshold_sensitivity_v1"

SWEEPS = {
    "tau_b": [0.15, 0.20, 0.25, 0.30],
    "theta_c": [0.05, 0.08, 0.12, 0.16],
    "c_refl": [0.30, 0.40, 0.50],
    "tau_carry": [0.30, 0.35, 0.40],
}


def generate_grid(one_at_a_time: bool = True) -> list[dict]:
    base = dict(BIOHARNESS_THRESHOLDS)
    grid: list[dict] = [{"name": "baseline", **base}]
    if one_at_a_time:
        for param, values in SWEEPS.items():
            for v in values:
                if v == base.get(param):
                    continue
                cfg = dict(base)
                cfg[param] = v
                cfg["name"] = f"{param}={v}"
                grid.append(cfg)
    else:
        keys = list(SWEEPS.keys())
        for combo in itertools.product(*[SWEEPS[k] for k in keys]):
            cfg = dict(base)
            for k, v in zip(keys, combo):
                cfg[k] = v
            cfg["name"] = "_".join(f"{k}={v}" for k, v in zip(keys, combo))
            grid.append(cfg)
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description="Threshold sensitivity grid generator")
    parser.add_argument("--dry-run", action="store_true", help="Write grid only (default)")
    parser.add_argument("--full-factorial", action="store_true")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    grid = generate_grid(one_at_a_time=not args.full_factorial)
    store = SupplementRunStore(args.out_root)
    payload = {
        "baseline": BIOHARNESS_THRESHOLDS,
        "sweep_mode": "full_factorial" if args.full_factorial else "one_at_a_time",
        "n_configs": len(grid),
        "configs": grid,
        "run_instructions": [
            "Map each config to harness YAML override (future: bio_harness/config overrides).",
            "Run eval/run_agentdojo_benchmark.py on stress 18 conditions × DeepSeek.",
            "Aggregate with eval/supplement/run_p0_peer_table.py pattern.",
        ],
        "estimate": {
            "batches_per_config": 18,
            "total_batches": len(grid) * 18,
            "wall_time_hours": f"{len(grid) * 18 * 0.25:.0f}–{len(grid) * 18 * 0.5:.0f} (rough)",
        },
    }
    store.write_json("p1", EXPERIMENT_ID, "grid.json", payload)
    print(f"Threshold grid ({len(grid)} configs) → {store.experiment_dir('p1', EXPERIMENT_ID)}")
    if args.dry_run:
        print("Dry-run: grid only. Pass --no-dry-run when runner wired to AgentDojo.")


if __name__ == "__main__":
    main()
