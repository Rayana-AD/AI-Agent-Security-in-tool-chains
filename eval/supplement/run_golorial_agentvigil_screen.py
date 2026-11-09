#!/usr/bin/env python3
"""No-defense screen of Golorial/agentvigil seeds on AgentDojo banking.

Uses their seed templates and evaluate_seed. If any seed hijacks the undefended
DeepSeek agent, continue with a short MCTS fuzz on that pair and replay the
best payload under bio_remeasure. If nothing lands, stop.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTO = ROOT / "third_party" / "AutoDojo" / "agentdojo"
VIGIL = ROOT / "third_party" / "agentvigil"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(AUTO / "src"), str(ROOT / "third_party")]
os.environ["AGENTDOJO_DEFENSE_PLUGINS"] = "eval.supplement.autodojo_plugin"
os.environ["PYTHONPATH"] = os.pathsep.join(
    [str(ROOT / "third_party"), str(AUTO / "src"), str(ROOT / "src"), str(ROOT), os.environ.get("PYTHONPATH", "")]
)

import eval.supplement.autodojo_plugin  # noqa: E402, F401
from eval.supplement.bootstrap_env import apply_secrets_to_env  # noqa: E402

_env = apply_secrets_to_env()
os.environ["DEEPSEEK_API_KEY"] = _env.get("DEEPSEEK_API_KEY", "")
os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
os.environ["OPENAI_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"

from openai import OpenAI  # noqa: E402
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
from agentvigil.agentvigil import FuzzConfig, run_fuzzing  # noqa: E402
from agentvigil.scoring import evaluate_seed  # noqa: E402
from agentvigil.seed_collector import collect_seeds  # noqa: E402

OUT = ROOT / "runs" / "supplement" / "p1" / "golorial_agentvigil_nodefense"
PAIRS = [
    ("user_task_0", "injection_task_0"),
    ("user_task_1", "injection_task_0"),
    ("user_task_2", "injection_task_0"),
]


def _pipeline(defense: str | None):
    return AgentPipeline.from_config(
        PipelineConfig(
            llm="deepseek-chat",
            model_id=None,
            defense=defense,
            suite_name="banking",
            system_message_name=None,
            system_message=None,
        )
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    suite = get_suite("v1.2.2", "banking")
    none = _pipeline(None)
    seeds = [s for s in collect_seeds(suite) if s["injection_task_id"] == "injection_task_0"]
    rows = []
    hits = []
    for user_task, inj in PAIRS:
        for seed in seeds:
            result = evaluate_seed(seed["prompt"], suite, none, user_task, inj)
            row = {
                "user_task": user_task,
                "template": seed["template_name"],
                "success": bool(result.get("success")),
                "utility": bool(result.get("utility")),
            }
            rows.append(row)
            if row["success"]:
                hits.append(row)
            print(
                f"none {user_task} {seed['template_name']}: "
                f"attack={row['success']} utility={row['utility']}",
                flush=True,
            )

    report = {
        "experiment": "golorial_agentvigil_nodefense_screen",
        "repo": "https://github.com/Golorial/agentvigil",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n": len(rows),
        "n_attack_success": len(hits),
        "rows": rows,
        "continued": False,
    }
    if not hits:
        (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("NO_DEFENSE_NOT_ATTACKED — stop", flush=True)
        return

    best = hits[0]
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com/v1")
    fuzz = run_fuzzing(
        suite,
        best["user_task"],
        "injection_task_0",
        none,
        client,
        FuzzConfig(n_iterations=4, n_mutations_per_iter=1, helper_model="deepseek-chat"),
    )
    bio = _pipeline("bio_remeasure")
    bio_result = evaluate_seed(fuzz.best_prompt, suite, bio, best["user_task"], "injection_task_0")
    report["continued"] = True
    report["fuzz_pair"] = best
    report["fuzz_best_asr"] = fuzz.best_asr
    report["bio_remeasure"] = {
        "success": bool(bio_result.get("success")),
        "utility": bool(bio_result.get("utility")),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"fuzz best asr={fuzz.best_asr:.0%} bio_attack={report['bio_remeasure']['success']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
