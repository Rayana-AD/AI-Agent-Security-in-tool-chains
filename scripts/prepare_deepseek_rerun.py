#!/usr/bin/env python3
"""Clear cached AgentDojo logs for DeepSeek cells that need re-run."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "agentdojo_upstream" / "benchmark_20260629_224640"
DEFENSES = ["none", "tool_filter", "repeat_user_prompt", "bio_idea1_provenance"]


def should_rerun(metrics: dict, *, utility_threshold: float, defense: str) -> bool:
    if not isinstance(metrics, dict):
        return False
    if metrics.get("error"):
        return True
    util = metrics.get("utility_pct")
    if util is None:
        util = (metrics.get("utility") or 0) * 100
    if defense == "bio_idea1_provenance" and util < utility_threshold:
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare DeepSeek benchmark re-run targets")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument(
        "--utility-threshold",
        type=float,
        default=50.0,
        help="Re-run bio_idea1_provenance suites below this utility %% (default 50)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report_path = args.run_dir / "report.json"
    if not report_path.exists():
        raise SystemExit(f"No report.json at {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    logs_root = args.run_dir / "logs"
    removed: list[str] = []

    for attack, by_defense in (report.get("results_by_attack") or {}).items():
        if not isinstance(by_defense, dict):
            continue
        for defense in DEFENSES:
            suites = by_defense.get(defense) or {}
            for suite, metrics in suites.items():
                if not should_rerun(metrics, utility_threshold=args.utility_threshold, defense=defense):
                    continue
                log_dir = logs_root / attack / defense / suite
                if log_dir.is_dir():
                    removed.append(str(log_dir.relative_to(args.run_dir)))
                    if not args.dry_run:
                        shutil.rmtree(log_dir)
                # Clear stale error/metrics so aggregate refreshes on next run.
                if isinstance(metrics, dict) and not args.dry_run:
                    suites[suite] = {}

    if not args.dry_run and removed:
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'Would remove' if args.dry_run else 'Removed'} {len(removed)} log trees:")
    for p in removed:
        print(f"  - {p}")
    if not removed:
        print("Nothing to clear.")


if __name__ == "__main__":
    main()
