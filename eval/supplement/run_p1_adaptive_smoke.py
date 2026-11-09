#!/usr/bin/env python3
"""P1: Write adaptive protocol artifact + optional smoke placeholder.

Full L3 integration targets AutoDojo (see docs/eval/GITHUB_REDTEAM_SURVEY.md).
This script registers protocol JSON and documents the smoke plan under runs/supplement/p1/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.protocol_adaptive import export_protocol
from eval.supplement.results_store import SupplementRunStore

EXPERIMENT_ID = "adaptive_protocol_v1"


def smoke_plan(dry_run: bool) -> dict:
    return {
        "status": "planned" if dry_run else "pending_execution",
        "integration_target": "https://github.com/xhOwenMa/AutoDojo",
        "local_fallback": "eval/supplement/run_p1_adaptive_smoke.py (this file)",
        "smoke_conditions": [
            "deepseek|important_instructions|injection_task_0|workspace",
            "deepseek|important_instructions_persona|injection_task_0|banking",
            "deepseek|direct|injection_task_0|slack",
        ],
        "budget": {"iterations": 3, "defenses": ["bio_04", "task_shield", "none"]},
        "estimated_episodes": 3 * 3 * 3,
        "estimated_api_hours": "4–8h (DeepSeek, depends on AgentDojo latency)",
        "next_steps": [
            "git submodule add AutoDojo or vendor adapter under eval/supplement/autodojo/",
            "Register bio_04 in AutoDojo defense registry",
            "Run smoke; write runs/supplement/p1/adaptive_protocol_v1/smoke/report.json",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P1 adaptive protocol smoke scaffold")
    parser.add_argument("--dry-run", action="store_true", help="Only write protocol + plan")
    parser.add_argument("--out-root", type=Path, default=None)
    args = parser.parse_args()

    store = SupplementRunStore(args.out_root)
    store.write_json("p1", EXPERIMENT_ID, "protocol.json", export_protocol())
    plan = smoke_plan(args.dry_run)
    store.write_json("p1", EXPERIMENT_ID, "smoke/plan.json", plan)

    readme = """# P1 Adaptive Red-Team

- Protocol: `protocol.json`
- Smoke plan: `smoke/plan.json`
- Full spec: `docs/eval/P1_ADAPTIVE_REDTEAM_PROTOCOL.md`
- GitHub survey: `docs/eval/GITHUB_REDTEAM_SURVEY.md`

Execute smoke after AutoDojo integration; do not claim adaptive ASR from plan.json alone.
"""
    store.write_text("p1", EXPERIMENT_ID, "README.md", readme)

    out = store.experiment_dir("p1", EXPERIMENT_ID)
    print(f"P1 protocol → {out}")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
