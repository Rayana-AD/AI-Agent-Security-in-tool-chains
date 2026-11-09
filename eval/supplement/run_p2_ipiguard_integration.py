#!/usr/bin/env python3
"""P2: IPIGuard integration scaffold (defense baseline, not yet wired)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "ipiguard_integration_v1"
IPIGUARD_REPO = "https://github.com/Greysahy/ipiguard"


def integration_plan() -> dict:
    return {
        "status": "scaffold",
        "defense": "IPIGuard",
        "paper": "an2025ipiguard",
        "repo": IPIGUARD_REPO,
        "type": "Tool Dependency Graph constraint (EMNLP 2025 Oral)",
        "integration_steps": [
            "Clone Greysahy/ipiguard; pin commit in runs/supplement/manifest.json",
            "Add eval/agentdojo/ipiguard_adapter.py wrapping their AgentDojo defense hook",
            "Register defense name `ipiguard` in pipeline_factory.py",
            "Run same 24-condition DeepSeek manifest as P0 peers",
            "Store under runs/supplement/p2/ipiguard_integration_v1/",
        ],
        "estimated_days": "4–7",
        "notes": "IPIGuard is a defense baseline; pair with P1 adaptive attack for bio_04 vs ipiguard.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P2 IPIGuard integration scaffold")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    store = SupplementRunStore(args.out_root)
    plan = integration_plan()
    store.write_json("p2", EXPERIMENT_ID, "plan.json", plan)
    store.write_text(
        "p2",
        EXPERIMENT_ID,
        "README.md",
        f"# IPIGuard integration\n\nRepo: {IPIGUARD_REPO}\n\nSee plan.json for steps.\n",
    )
    print(f"P2 ipiguard scaffold → {store.experiment_dir('p2', EXPERIMENT_ID)}")


if __name__ == "__main__":
    main()
