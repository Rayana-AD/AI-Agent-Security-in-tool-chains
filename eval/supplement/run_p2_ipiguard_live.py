#!/usr/bin/env python3
"""P2: IPIGuard live smoke on AgentDojo (official ipiguard/agentdojo fork)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.bootstrap_env import ensure_venv_python, env_for_ipiguard, git_head, repo_root

ensure_venv_python()

EXPERIMENT_ID = "ipiguard_live_v1"
IPI_ROOT = repo_root() / "third_party" / "ipiguard"


def _prep_ipiguard_imports() -> None:
    """Prefer ipiguard's vendored agentdojo over pip-installed agentdojo."""
    for name in list(sys.modules):
        if name == "agentdojo" or name.startswith("agentdojo."):
            del sys.modules[name]


def _load_ipiguard_eval():
    env = env_for_ipiguard()
    for k, v in env.items():
        os.environ[k] = v
    _prep_ipiguard_imports()
    ipi_src = str(IPI_ROOT / "agentdojo" / "src")
    ipi_run = str(IPI_ROOT / "run")
    for p in (ipi_run, ipi_src):
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("ipiguard_eval", IPI_ROOT / "run" / "eval.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_smoke_inprocess(
    *,
    suite: str,
    user_task_id: int,
    injection_task_id: int,
    agent_model: str,
    attack: str,
    defense: str,
) -> dict:
    """Run exactly one (user_task, injection_task) pair."""
    ipi_eval = _load_ipiguard_eval()
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.models import ModelsEnum
    from agentdojo.task_suite.load_suites import get_suite
    suite_obj = get_suite("v1.1.2", suite)
    model = ModelsEnum(agent_model)
    if defense.lower() == "none":
        pipeline = AgentPipeline.from_config(
            PipelineConfig(llm=model, defense=None, system_message_name=None, system_message=None)
        )
    else:
        pipeline = AgentPipeline.from_config(
            PipelineConfig(llm=model, defense=defense, system_message_name=None, system_message=None)
        )
    attacker = load_attack(attack, suite_obj, pipeline)
    user_task = suite_obj.get_user_task_by_id(f"user_task_{user_task_id}")
    injection_task = suite_obj.get_injection_task_by_id(f"injection_task_{injection_task_id}")
    attacks = attacker.attack(user_task, injection_task)
    security, utility, messages = ipi_eval.AgentTask.run(
        pipeline, suite_obj, attacks, user_task, injection_task, extra_args={}
    )
    return {
        "suite": suite,
        "user_task_id": user_task_id,
        "injection_task_id": injection_task_id,
        "agent_model": agent_model,
        "attack": attack,
        "defense": defense,
        "asr": int(security),
        "utility": int(utility),
        "n_messages": len(messages or []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="IPIGuard live smoke")
    parser.add_argument("--execute", action="store_true", help="Run live API cell")
    parser.add_argument("--suite", default="workspace")
    parser.add_argument("--user-task-id", type=int, default=0)
    parser.add_argument("--injection-task-id", type=int, default=0)
    parser.add_argument(
        "--agent-model",
        default=os.environ.get("IPIGUARD_SMOKE_MODEL", "deepseek-ai/DeepSeek-V3"),
    )
    parser.add_argument("--attack", default="important_instructions")
    parser.add_argument("--defense", default="ipiguard")
    args = parser.parse_args()

    from eval.supplement.results_store import SupplementRunStore

    store = SupplementRunStore()
    report = {
        "experiment_id": EXPERIMENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ipiguard_commit": git_head(IPI_ROOT),
        "repo": "https://github.com/Greysahy/ipiguard",
        "python": sys.version,
        "status": "planned",
    }

    if args.execute:
        try:
            report["smoke_cell"] = run_smoke_inprocess(
                suite=args.suite,
                user_task_id=args.user_task_id,
                injection_task_id=args.injection_task_id,
                agent_model=args.agent_model,
                attack=args.attack,
                defense=args.defense,
            )
            report["status"] = "smoke_ok"
        except Exception as exc:
            report["status"] = "smoke_failed"
            report["error"] = str(exc)

    store.write_json("p2", EXPERIMENT_ID, "report.json", report)
    print(json.dumps(report, indent=2))
    print(f"\nP2 IPIGuard live → {store.experiment_dir('p2', EXPERIMENT_ID)}")
    if report["status"] == "smoke_failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
