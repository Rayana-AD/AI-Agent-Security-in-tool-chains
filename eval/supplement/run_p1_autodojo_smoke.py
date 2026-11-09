#!/usr/bin/env python3
"""P1 L3: AutoDojo integration verify + optional smoke benchmark."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.bootstrap_env import ensure_venv_python, env_for_autodojo, git_head

ensure_venv_python()

AUTODOJO_SRC = ROOT / "third_party" / "AutoDojo" / "agentdojo" / "src"
EXPERIMENT_ID = "adaptive_autodojo_v1"


def verify_plugin() -> dict:
    env = env_for_autodojo()
    code = """
import os, sys
from agentdojo.agent_pipeline.agent_pipeline import DEFENSES, DEFENSE_FACTORIES
ok = "bio_04" in DEFENSES and "bio_04" in DEFENSE_FACTORIES
print("OK" if ok else "FAIL")
print("DEFENSES_has_bio_04", "bio_04" in DEFENSES)
print("FACTORIES", sorted(DEFENSE_FACTORIES.keys()))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-500:] if proc.stderr else "",
        "plugin_ok": "OK" in proc.stdout and proc.returncode == 0,
    }


def smoke_plan() -> dict:
    plan_path = ROOT / "runs/supplement/p1/adaptive_protocol_v1/smoke/plan.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text(encoding="utf-8"))
    return {}


def run_benchmark_smoke(*, suite: str, user_task: str, defense: str, logdir: Path) -> dict:
    env = env_for_autodojo()
    model_mode = os.environ.get("AUTODOJO_SMOKE_MODEL_MODE", "deepseek")
    cmd = [
        sys.executable,
        str(ROOT / "eval" / "run_agentdojo_benchmark.py"),
        "--model-mode",
        model_mode,
        "--suite",
        suite,
        "--user-task",
        user_task,
        "--injection-task",
        "injection_task_0",
        "--attack",
        "important_instructions",
        "--defense",
        defense,
        "--logdir",
        str(logdir),
        "--force-rerun",
    ]
    proc = subprocess.run(cmd, env=env, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-800:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-800:] if proc.stderr else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDojo L3 smoke")
    parser.add_argument("--verify-only", action="store_true", help="Only verify plugin registration")
    parser.add_argument("--execute", action="store_true", help="Run 1 live benchmark cell (needs API key)")
    parser.add_argument("--defense", default="bio_04")
    parser.add_argument("--suite", default="workspace")
    parser.add_argument("--user-task", default="user_task_0")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from eval.supplement.results_store import SupplementRunStore

    store = SupplementRunStore()
    autodojo_root = ROOT / "third_party" / "AutoDojo"
    verification = verify_plugin()
    report = {
        "experiment_id": EXPERIMENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "autodojo_commit": git_head(autodojo_root),
        "python": sys.version,
        "plugin_module": "eval.supplement.autodojo_plugin",
        "verify": verification,
        "smoke_plan": smoke_plan(),
        "status": "verified" if verification.get("plugin_ok") else "verify_failed",
    }

    if args.execute and not args.verify_only:
        logdir = store.experiment_dir("p1", EXPERIMENT_ID) / "benchmark_logs"
        logdir.mkdir(parents=True, exist_ok=True)
        report["benchmark_smoke"] = run_benchmark_smoke(
            suite=args.suite,
            user_task=args.user_task,
            defense=args.defense,
            logdir=logdir,
        )
        report["status"] = (
            "smoke_ok" if report["benchmark_smoke"]["returncode"] == 0 else "smoke_failed"
        )

    store.write_json("p1", EXPERIMENT_ID, "report.json", report)
    out = store.experiment_dir("p1", EXPERIMENT_ID)
    print(json.dumps(report, indent=2))
    print(f"\nP1 AutoDojo → {out}")
    if not report["verify"].get("plugin_ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
