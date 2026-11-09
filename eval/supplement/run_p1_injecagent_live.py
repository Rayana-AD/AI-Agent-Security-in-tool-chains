#!/usr/bin/env python3
"""P1: InjecAgent live smoke (DeepSeek) with optional bio_04 tool-response guard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.bootstrap_env import ensure_venv_python, env_for_injecagent, git_head, repo_root

ensure_venv_python()

EXPERIMENT_ID = "injecagent_live_v1"
INJ_ROOT = repo_root() / "third_party" / "InjecAgent"


def _setup_injecagent_env(*, prefer_deepseek_native: bool = True) -> None:
    env = env_for_injecagent()
    if prefer_deepseek_native:
        import yaml

        secrets = yaml.safe_load((repo_root() / "configs" / "secrets.yaml").read_text(encoding="utf-8")) or {}
        if secrets.get("deepseek_api_key"):
            env["OPENAI_API_KEY"] = str(secrets["deepseek_api_key"])
            env["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"
            env["DEEPSEEK_API_KEY"] = str(secrets["deepseek_api_key"])
    for k, v in env.items():
        os.environ[k] = v
    inj = str(INJ_ROOT)
    if inj not in sys.path:
        sys.path.insert(0, inj)


def _sanitize_tool_response(text: str, *, defense: str) -> tuple[str, bool]:
    """Optional bio_04: strip injection envelope from tool observation before agent step 2."""
    if defense != "bio_04":
        return text, False
    from bio_harness.harness.graph import build_runner
    from eval.agentdojo.ipi_output_modes import detect_injection_envelope, strip_injection_envelope

    if detect_injection_envelope(text):
        return (
            strip_injection_envelope(text)
            or "<Tool output withheld: injection envelope detected by bio_04.>",
            True,
        )
    runner = build_runner("idea1_provenance_mlp_bio_remeasure")
    fold = runner.fold.fold(text, session_id="injecagent", probe_count=0)
    if not fold.passed:
        return "<Tool output withheld: bio_04 fold blocked.>", True
    return fold.reconstructed, False


def run_smoke(
    *,
    model_name: str,
    setting: str,
    attack: str,
    max_cases: int,
    defense: str,
) -> dict:
    _setup_injecagent_env()
    os.chdir(INJ_ROOT)
    from tqdm import tqdm

    from eval.injecagent.deepseek_model import DeepSeekModel
    from src.models import MODELS
    from src.output_parsing import evaluate_output_prompted
    from src.prompts.agent_prompts import PROMPT_DICT
    from src.utils import get_tool_dict

    MODELS["DeepSeek"] = DeepSeekModel
    params = {
        "model_type": "DeepSeek",
        "model_name": model_name,
        "setting": setting,
        "prompt_type": "InjecAgent",
        "use_cache": False,
        "only_get_score": False,
    }
    model_class = MODELS["DeepSeek"](params)
    system_prompt, user_prompt = PROMPT_DICT["InjecAgent"]
    tool_dict = get_tool_dict()

    data_path = INJ_ROOT / "data" / f"test_cases_{attack}_{setting}.json"
    cases = json.loads(data_path.read_text(encoding="utf-8"))[:max_cases]

    rows = []
    for item in tqdm(cases, desc="InjecAgent smoke"):
        tool_response = item["Tool Response"]
        sanitized, blocked = _sanitize_tool_response(tool_response, defense=defense)
        item_run = dict(item)
        if blocked:
            item_run["Tool Response"] = sanitized

        available_tool_names = [item_run["User Tool"]] + item_run["Attacker Tools"]
        available_tool_descriptions = json.dumps(
            [tool_dict[t] for t in available_tool_names], indent=True
        )
        agent_scratchpad = (
            f"\n{item_run['Thought']}\nAction: {item_run['User Tool']}\n"
            f"Action Input: {item_run['Tool Parameters']}\nObservation: {item_run['Tool Response']}\n"
        )
        user_prompt_filled = user_prompt.format(
            available_tool_descriptions=available_tool_descriptions,
            input=item_run["User Instruction"],
            available_tool_names=available_tool_names,
            agent_scratchpad=agent_scratchpad,
        )
        model_input = model_class.prepare_input(system_prompt, user_prompt_filled)
        output = model_class.call_model(model_input)
        parsed = evaluate_output_prompted(
            output,
            item_run["Attacker Tools"][0],
            item_run["Attacker Tools"],
            item_run["User Tool"],
            item_run["Attacker Instruction"],
        )
        rows.append(
            {
                "user_instruction": item_run["User Instruction"][:120],
                "eval": parsed.get("eval"),
                "defense_blocked_observation": blocked,
                "output_preview": (output or "")[:200],
            }
        )

    valid = [r for r in rows if r["eval"] != "invalid"]
    success = [r for r in valid if r["eval"] == "success"]
    return {
        "model_name": model_name,
        "setting": setting,
        "attack_file": attack,
        "defense": defense,
        "n_cases": len(rows),
        "n_valid": len(valid),
        "asr_valid": round(len(success) / max(len(valid), 1), 4),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="InjecAgent live smoke")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--model-name", default="deepseek-chat")
    parser.add_argument("--setting", default="base", choices=("base", "enhanced"))
    parser.add_argument("--attack", default="dh", choices=("dh", "ds"))
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--defense", default="none", choices=("none", "bio_04"))
    parser.add_argument("--experiment-id", default=EXPERIMENT_ID)
    args = parser.parse_args()

    from eval.supplement.results_store import SupplementRunStore

    store = SupplementRunStore()
    report = {
        "experiment_id": args.experiment_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "injecagent_commit": git_head(INJ_ROOT),
        "repo": "https://github.com/uiuc-kang-lab/InjecAgent",
        "python": sys.version,
        "status": "planned",
    }

    if args.execute:
        try:
            report["smoke"] = run_smoke(
                model_name=args.model_name,
                setting=args.setting,
                attack=args.attack,
                max_cases=args.max_cases,
                defense=args.defense,
            )
            report["status"] = "smoke_ok"
        except Exception as exc:
            report["status"] = "smoke_failed"
            report["error"] = str(exc)

    stem = f"report_{args.attack}_{args.defense}.json"
    store.write_json("p1", args.experiment_id, stem, report)
    print(json.dumps({k: v for k, v in report.items() if k != "smoke" or not isinstance(v, dict) or "rows" not in v}, indent=2)[:4000])
    print(f"\nP1 InjecAgent live → {store.experiment_dir('p1', args.experiment_id) / stem}")
    if report["status"] == "smoke_failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
