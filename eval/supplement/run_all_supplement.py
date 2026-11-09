#!/usr/bin/env python3
"""Orchestrate P0–P2 supplement scaffolds (safe defaults: P0 export + dry-run plans)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "eval" / "supplement"


def run(script: str, *extra: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), *extra]
    print("\n>>>", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run supplement pipeline")
    parser.add_argument("--phase", choices=["p0", "p1", "p2", "all"], default="all")
    parser.add_argument("--execute-p2", action="store_true", help="Run P2 harness (not just dry-run)")
    args = parser.parse_args()

    if args.phase in ("p0", "all"):
        run("run_p0_peer_table.py")

    if args.phase in ("p1", "all"):
        run("run_p1_adaptive_smoke.py", "--dry-run")
        run("run_p2_threshold_sensitivity.py")
        if args.execute_p2:
            run("run_p1_adaptive_l2.py")
        else:
            run("run_p1_adaptive_l2.py", "--dry-run")

    if args.phase in ("p2", "all"):
        run("run_p2_ipiguard_integration.py")
        if args.execute_p2:
            run("run_comparison_matrix.py")
            run("visualize_supplement_results.py")
            run("run_p2_path_smuggle.py")
            run("run_p2_multi_hop_carry.py")
            run("run_p2_atomic_retry.py")
            run("run_p2_mhj_temporal.py", "--limit", "10")
            run("run_p2_idea2_summary.py")
        else:
            run("run_p2_path_smuggle.py", "--dry-run")
            run("run_p2_multi_hop_carry.py", "--dry-run")
            run("run_p2_atomic_retry.py", "--dry-run")
            run("run_p2_mhj_temporal.py", "--dry-run", "--limit", "10")
            run("run_p2_idea2_summary.py", "--dry-run")

    print("\nDone. Index: runs/supplement/manifest.json")


if __name__ == "__main__":
    main()
