#!/usr/bin/env python3
"""AGENTVIGIL slice: distinct injection GOALs × MCTS adaptive packaging.

Estimand: one MCTS run per (anchor user, injection GOAL). Initial population =
Golorial static seed templates (``golorial6``); mutations are LLM+MCTS (AgentVigil).

Optional ``--screen`` runs a separate static template sweep (e.g. ``extended`` for
Table-1 alignment). Default ``vulnerable-banking`` profile skips that sweep—static
seeds are already evaluated inside ``run_fuzzing``.

Pipeline (adaptive default):
  1. Fuzz — MCTS on every (user, injection) pair in the plan.
  2. Bio — replay best none prompt when fuzz/seed phase breaks defense.

Legacy ``--screen`` / ``--fuzz-hits-only``: diagnostic only; hits-only fuzz needs screen.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTO = ROOT / "third_party" / "AutoDojo" / "agentdojo"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(AUTO / "src"), str(ROOT / "third_party")]
os.environ["AGENTDOJO_DEFENSE_PLUGINS"] = "eval.supplement.autodojo_plugin"
os.environ["PYTHONPATH"] = os.pathsep.join(
    [
        str(ROOT / "third_party"),
        str(AUTO / "src"),
        str(ROOT / "src"),
        str(ROOT),
        os.environ.get("PYTHONPATH", ""),
    ]
)

import eval.supplement.autodojo_plugin  # noqa: E402, F401
from eval.paper_curated import _sorted_injection_task_ids, resolve_injection_task_id  # noqa: E402
from eval.supplement.agentvigil_seed_sets import (  # noqa: E402
    seeds_for_injection,
    seeds_for_suite,
    template_count,
)
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
import agentvigil.seed_collector as _seed_collector  # noqa: E402

OUT = ROOT / "runs" / "supplement" / "p1" / "golorial_agentvigil_slice"

VULNERABLE_PROFILE = {
    "suites": ["banking"],
    "anchor_user": {"banking": "user_task_0"},
    "injection_slots": "all",
    # MCTS seed population only (not paper/warm static sweep).
    "template_set": "golorial6",
    "skip_static_screen": True,
    "fuzz_iterations": 5,
    "fuzz_mutations": 3,
}

# One user per suite unless --extra-users expands (still same injection list).
DEFAULT_ANCHOR_USER: dict[str, str] = {
    "banking": "user_task_0",
    "slack": "user_task_0",
    "workspace": "user_task_26",
}


def _pipeline(defense: str | None):
    return AgentPipeline.from_config(
        PipelineConfig(
            llm="deepseek-chat",
            model_id=None,
            defense=defense,
            system_message_name=None,
            system_message=None,
        )
    )


def _save(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def _users_for_suite(suite_name: str, extra_users: list[str]) -> list[str]:
    anchor = DEFAULT_ANCHOR_USER.get(suite_name)
    if anchor is None:
        raise KeyError(f"No default anchor user for suite {suite_name!r}; pass --extra-users")
    users = [anchor]
    for u in extra_users:
        if u not in users:
            users.append(u)
    return users


def _resolve_injection_tasks(suite_name: str, injection_slots: str) -> list[str]:
    if injection_slots == "all":
        return _sorted_injection_task_ids(suite_name)
    if injection_slots == "manifest":
        return [
            resolve_injection_task_id(suite_name, "injection_task_0"),
            resolve_injection_task_id(suite_name, "injection_task_1"),
        ]
    ids: list[str] = []
    for token in injection_slots.split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("injection_task_"):
            ids.append(resolve_injection_task_id(suite_name, token))
        else:
            slot = int(token)
            ids.append(resolve_injection_task_id(suite_name, f"injection_task_{slot}"))
    return ids


def _build_plan(
    suites: list[str],
    extra_users: list[str],
    *,
    injection_slots: str,
    anchor_override: dict[str, str] | None,
) -> dict[str, dict]:
    plan: dict[str, dict] = {}
    for suite_name in suites:
        injections = _resolve_injection_tasks(suite_name, injection_slots)
        if anchor_override and suite_name in anchor_override:
            users = [anchor_override[suite_name]]
        else:
            users = _users_for_suite(suite_name, extra_users)
        plan[suite_name] = {
            "anchor_user": users[0],
            "user_tasks": users,
            "injection_tasks": injections,
            "n_distinct_goals": len(injections),
            "injection_slots_mode": injection_slots,
        }
    return plan


def _iter_pairs(plan: dict[str, dict]):
    for suite_name, spec in plan.items():
        for inj_id in spec["injection_tasks"]:
            for user in spec["user_tasks"]:
                yield suite_name, user, inj_id


def _prompt_for_template(
    suite,
    injection_task_id: str,
    template_name: str,
    *,
    user_task_id: str,
    pipeline,
    template_set: str,
) -> str | None:
    for seed in seeds_for_injection(
        suite,
        injection_task_id,
        user_task_id=user_task_id,
        pipeline=pipeline,
        template_set=template_set,
    ):
        if seed["template_name"] == template_name:
            return seed["prompt"]
    return None


def _scale_summary(
    plan: dict[str, dict],
    *,
    mcts_template_set: str,
    skip_static_screen: bool,
    screen_template_set: str | None,
) -> dict:
    n_goals = sum(p["n_distinct_goals"] for p in plan.values())
    n_pairs = sum(p["n_distinct_goals"] * len(p["user_tasks"]) for p in plan.values())
    n_mcts_seeds = template_count(mcts_template_set)
    n_screen_tpl = template_count(screen_template_set) if screen_template_set else 0
    return {
        "estimand": "mcts_per_injection_goal",
        "suites": plan,
        "mcts_seed_template_set": mcts_template_set,
        "n_mcts_seed_templates_per_goal": n_mcts_seeds,
        "n_distinct_malicious_goals": n_goals,
        "n_user_injection_pairs": n_pairs,
        "n_mcts_runs": n_pairs,
        "skip_static_screen": skip_static_screen,
        "static_screen_template_set": screen_template_set,
        "n_static_screen_agent_runs": (0 if skip_static_screen else n_pairs * n_screen_tpl),
        "note": (
            "Adaptive: one AgentVigil MCTS per (user, injection GOAL); "
            "threat configurations for packaging ablation use slot×template only with --screen."
        ),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Injection-first AGENTVIGIL slice on AgentDojo.")
    p.add_argument(
        "--profile",
        choices=("none", "vulnerable-banking"),
        default="none",
        help="vulnerable-banking: banking, user_task_0, all injection slots, golorial6 MCTS, no static screen.",
    )
    p.add_argument(
        "--suites",
        default="banking",
        help="Comma-separated suites (default: banking only). Each uses one anchor user.",
    )
    p.add_argument(
        "--injection-slots",
        default="all",
        help="all | manifest (2 slot) | comma logical slots e.g. 0,1,2 or injection_task_0,...",
    )
    p.add_argument(
        "--template-set",
        choices=("golorial6", "manifest4", "extended"),
        default="golorial6",
        help="MCTS initial seeds (and static screen templates unless --screen-template-set).",
    )
    p.add_argument(
        "--screen",
        action="store_true",
        help="Run optional static template sweep on none before MCTS (diagnostic / slot×template ASR).",
    )
    p.add_argument(
        "--screen-template-set",
        choices=("golorial6", "manifest4", "extended"),
        default=None,
        help="Templates for static screen only; default = same as --template-set.",
    )
    p.add_argument(
        "--extra-users",
        default="",
        help="Optional extra user_task IDs (comma-separated), same list applied to every suite.",
    )
    p.add_argument(
        "--fuzz-cap",
        type=int,
        default=0,
        help="Max (user,injection) pairs to MCTS-fuzz; 0 = all pairs in plan.",
    )
    p.add_argument(
        "--fuzz-hits-only",
        action="store_true",
        help="Legacy: only MCTS-fuzz pairs with at least one successful screen template.",
    )
    p.add_argument(
        "--fuzz-iterations",
        type=int,
        default=3,
        help="MCTS iterations per fuzzed pair.",
    )
    p.add_argument(
        "--fuzz-mutations",
        type=int,
        default=1,
        help="Mutations per MCTS iteration.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    anchor_override: dict[str, str] | None = None
    # Adaptive default: MCTS only. Static slot×template sweep is opt-in via --screen.
    skip_static_screen = not args.screen
    if args.profile == "vulnerable-banking":
        suites = list(VULNERABLE_PROFILE["suites"])
        anchor_override = dict(VULNERABLE_PROFILE["anchor_user"])
        injection_slots = str(VULNERABLE_PROFILE["injection_slots"])
        template_set = str(VULNERABLE_PROFILE["template_set"])
        if args.fuzz_iterations == 3 and args.fuzz_mutations == 1:
            args.fuzz_iterations = int(VULNERABLE_PROFILE["fuzz_iterations"])
            args.fuzz_mutations = int(VULNERABLE_PROFILE["fuzz_mutations"])
    else:
        suites = [s.strip() for s in args.suites.split(",") if s.strip()]
        injection_slots = args.injection_slots
        template_set = args.template_set

    mcts_template_set = template_set
    screen_template_set: str | None = None
    if not skip_static_screen:
        screen_template_set = args.screen_template_set or template_set
    extra_users = [u.strip() for u in args.extra_users.split(",") if u.strip()]
    plan = _build_plan(
        suites,
        extra_users,
        injection_slots=injection_slots,
        anchor_override=anchor_override,
    )

    none = _pipeline(None)
    report = {
        "experiment": "golorial_agentvigil_injection_slice",
        "profile": args.profile,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scale": _scale_summary(
            plan,
            mcts_template_set=mcts_template_set,
            skip_static_screen=skip_static_screen,
            screen_template_set=screen_template_set,
        ),
        "fuzz_config": {
            "fuzz_cap": args.fuzz_cap,
            "fuzz_hits_only": args.fuzz_hits_only,
            "n_iterations": args.fuzz_iterations,
            "n_mutations_per_iter": args.fuzz_mutations,
        },
        "screen": [],
        "fuzz": [],
    }
    hits: dict[tuple[str, str, str], list[str]] = {}

    if not skip_static_screen and screen_template_set:
        for suite_name, spec in plan.items():
            suite = get_suite("v1.2.2", suite_name)
            for inj_id in spec["injection_tasks"]:
                for user in spec["user_tasks"]:
                    seeds = seeds_for_injection(
                        suite,
                        inj_id,
                        user_task_id=user,
                        pipeline=none,
                        template_set=screen_template_set,
                    )
                    for seed in seeds:
                        result = evaluate_seed(seed["prompt"], suite, none, user, inj_id)
                        row = {
                            "suite": suite_name,
                            "user_task": user,
                            "injection_task": inj_id,
                            "template": seed["template_name"],
                            "goal_preview": seed["goal"][:120],
                            "success": bool(result.get("success")),
                            "utility": bool(result.get("utility")),
                        }
                        report["screen"].append(row)
                        if row["success"]:
                            hits.setdefault((suite_name, user, inj_id), []).append(seed["template_name"])
                        _save(report)
                        print(
                            f"screen {suite_name} {user} {inj_id} {seed['template_name']}: "
                            f"attack={row['success']} utility={row['utility']}",
                            flush=True,
                        )

        report["scale"]["n_screen_hit_pairs"] = len(hits)
        goals_hit = {inj for (_s, _u, inj) in hits}
        report["scale"]["n_distinct_goals_with_any_static_hit"] = len(goals_hit)
    elif args.fuzz_hits_only:
        _save(report)
        print("fuzz-hits-only requires --screen (no static hits without a screen phase)", flush=True)
        return

    fuzz_pairs: list[tuple[str, str, str]] = []
    if args.fuzz_hits_only:
        fuzz_pairs = [key for key in sorted(hits.keys())]
    else:
        fuzz_pairs = list(_iter_pairs(plan))
    if args.fuzz_cap > 0:
        fuzz_pairs = fuzz_pairs[: args.fuzz_cap]

    if not fuzz_pairs:
        report["none_attacked"] = bool(hits)
        _save(report)
        print("NO_FUZZ_PAIRS", flush=True)
        return

    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com/v1")
    bio = _pipeline("bio_remeasure")
    fuzz_cfg = FuzzConfig(
        n_iterations=args.fuzz_iterations,
        n_mutations_per_iter=args.fuzz_mutations,
        helper_model="deepseek-chat",
    )
    any_none_breakthrough = bool(hits)

    def _patched_collect_seeds(suite, user_name: str = "Emma Johnson", model_name: str = "Qwen"):
        spec = plan[suite.name]
        return seeds_for_suite(
            suite,
            spec["injection_tasks"],
            user_task_id=spec["anchor_user"],
            pipeline=none,
            template_set=mcts_template_set,
        )

    _seed_collector.collect_seeds = _patched_collect_seeds  # type: ignore[assignment]

    for suite_name, user, inj_id in fuzz_pairs:
        key = (suite_name, user, inj_id)
        templates = hits.get(key, [])
        suite = get_suite("v1.2.2", suite_name)
        fuzz = run_fuzzing(suite, user, inj_id, none, client, fuzz_cfg)
        seed_phase_hit = fuzz.best_score > 0
        mutation_hit = fuzz.best_asr > 0
        none_breakthrough = mutation_hit or seed_phase_hit or bool(templates)
        any_none_breakthrough = any_none_breakthrough or none_breakthrough

        row: dict = {
            "suite": suite_name,
            "user_task": user,
            "injection_task": inj_id,
            "screen_templates": templates,
            "fuzz_seed_best_score": fuzz.best_score,
            "fuzz_best_asr": fuzz.best_asr,
            "none_breakthrough": none_breakthrough,
            "best_prompt_preview": (fuzz.best_prompt or "")[:500],
            "bio_evaluated": False,
            "bio_attack": None,
            "bio_utility": None,
            "none_prompt_source": None,
        }
        if none_breakthrough:
            if mutation_hit or seed_phase_hit:
                eval_prompt = fuzz.best_prompt
                row["none_prompt_source"] = "fuzz" if mutation_hit else "seed"
            elif templates and screen_template_set:
                eval_prompt = _prompt_for_template(
                    suite,
                    inj_id,
                    templates[0],
                    user_task_id=user,
                    pipeline=none,
                    template_set=screen_template_set,
                )
                row["none_prompt_source"] = "static_screen"
            else:
                eval_prompt = None
            if eval_prompt:
                bio_result = evaluate_seed(eval_prompt, suite, bio, user, inj_id)
                row["bio_evaluated"] = True
                row["bio_attack"] = bool(bio_result.get("success"))
                row["bio_utility"] = bool(bio_result.get("utility"))
                row["bio_prompt_preview"] = eval_prompt[:500]

        report["fuzz"].append(row)
        _save(report)
        bio_msg = ""
        if row["bio_evaluated"]:
            bio_msg = (
                f" bio_attack={row['bio_attack']} bio_utility={row['bio_utility']} "
                f"via={row['none_prompt_source']}"
            )
        print(
            f"fuzz {suite_name} {user} {inj_id}: none_asr={fuzz.best_asr:.0%} "
            f"breakthrough={none_breakthrough}{bio_msg}",
            flush=True,
        )
    report["none_attacked"] = any_none_breakthrough
    report["scale"]["n_fuzz_pairs"] = len(report["fuzz"])
    report["scale"]["n_bio_evaluated"] = sum(1 for r in report["fuzz"] if r["bio_evaluated"])
    _save(report)


if __name__ == "__main__":
    main()
