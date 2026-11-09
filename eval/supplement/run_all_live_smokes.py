#!/usr/bin/env python3
"""Run AutoDojo + InjecAgent + IPIGuard live smoke cells (uses .venv Python >=3.10)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
SCRIPTS = [
    ("autodojo", "eval/supplement/run_p1_autodojo_smoke.py", ["--execute", "--defense", "bio_04"]),
    ("injecagent", "eval/supplement/run_p1_injecagent_live.py", ["--execute", "--max-cases", "3", "--defense", "bio_04"]),
    (
        "ipiguard",
        "eval/supplement/run_p2_ipiguard_live.py",
        ["--execute", "--defense", "ipiguard", "--agent-model", "deepseek-ai/DeepSeek-V3"],
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all supplement live smokes")
    parser.add_argument("--only", nargs="+", choices=[s[0] for s in SCRIPTS], help="Subset to run")
    args = parser.parse_args()

    if not PY.is_file():
        raise SystemExit(f"Missing {PY} — run: python3.11 -m venv .venv && .venv/bin/pip install -e '.[agentdojo]'")

    selected = [s for s in SCRIPTS if not args.only or s[0] in args.only]
    results = {}
    for name, rel, extra in selected:
        cmd = [str(PY), str(ROOT / rel), *extra]
        proc = subprocess.run(cmd, cwd=str(ROOT))
        results[name] = {"command": " ".join(cmd), "returncode": proc.returncode}

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "results": results,
        "all_ok": all(r["returncode"] == 0 for r in results.values()),
    }
    out_path = ROOT / "runs/supplement/live_smokes_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["all_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
