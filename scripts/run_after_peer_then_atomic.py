#!/usr/bin/env python3
"""Wait for peer baselines to finish, then launch the atomic_split slice.

Polls runs/paper_peer_baselines_deepseek_progress.json until 24 completed
batches (or peer process exits with a summary), then runs m1_atomic_slice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEER_PROGRESS = ROOT / "runs" / "paper_peer_baselines_deepseek_progress.json"
PEER_SUMMARY = ROOT / "runs" / "paper_peer_baselines_deepseek_progress_summary.json"
ATOMIC_PROGRESS = ROOT / "runs" / "paper_atomic_slice_deepseek_progress.json"
EXPECTED_PEER = 24


def peer_done(expected: int = EXPECTED_PEER) -> tuple[bool, int]:
    if not PEER_PROGRESS.exists():
        return False, 0
    try:
        d = json.loads(PEER_PROGRESS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, 0
    completed = {
        k: v
        for k, v in (d.get("completed") or {}).items()
        if ":stress_probe" not in k
    }
    n = len(completed)
    # Also treat presence of summary as done if n matches.
    if PEER_SUMMARY.exists() and n >= expected:
        return True, n
    return n >= expected, n


def peer_process_alive() -> bool:
    # Match the orchestrator, not arbitrary agentdojo jobs.
    try:
        out = subprocess.check_output(["pgrep", "-fl", "run_peer_baselines"], text=True)
        return "run_peer_baselines.py" in out
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--expected-peer-batches", type=int, default=EXPECTED_PEER)
    parser.add_argument("--skip-wait", action="store_true", help="Start atomic immediately")
    parser.add_argument("--atomic-max-batches", type=int, default=99)
    args = parser.parse_args()

    if not args.skip_wait:
        print(
            f"Waiting for peer baselines ({args.expected_peer_batches} completed)...",
            flush=True,
        )
        while True:
            done, n = peer_done(args.expected_peer_batches)
            alive = peer_process_alive()
            print(
                f"  peer completed={n}/{args.expected_peer_batches} alive={alive}",
                flush=True,
            )
            if done:
                break
            if not alive and n > 0 and n < args.expected_peer_batches:
                print(
                    f"WARN peer process exited early with {n} batches; "
                    "launching atomic on available peer results anyway.",
                    flush=True,
                )
                # Still summarize peer if possible.
                break
            if not alive and n == 0:
                print("WARN peer not running and no progress; waiting anyway...", flush=True)
            time.sleep(args.poll_seconds)

        # Best-effort peer summarize.
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-u",
                    str(ROOT / "scripts" / "run_peer_baselines.py"),
                    "--summarize-only",
                    "--progress-file",
                    str(PEER_PROGRESS),
                ],
                cwd=ROOT,
                check=False,
            )
        except Exception as e:
            print(f"peer summarize skipped: {e}", flush=True)

    print("\n=== Starting atomic_split slice ===", flush=True)
    log = ROOT / "logs" / "atomic_slice_deepseek.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "run_atomic_slice.py"),
        "--profile",
        "m1_atomic_slice",
        "--progress-file",
        str(ATOMIC_PROGRESS),
        "--max-batches",
        str(args.atomic_max_batches),
    ]
    print(" ".join(cmd), flush=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# start {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        fh.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
