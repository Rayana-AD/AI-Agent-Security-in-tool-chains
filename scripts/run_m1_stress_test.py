#!/usr/bin/env python3
"""Run M1 adaptive-IPI stress slice (slack + injection_task_1 + persona attacks)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from eval.paper_curated import load_curated_profile, resolve_injection_task_id
from eval.run_paper_suite import collect_live_from_benchmarks, load_progress, save_progress, suite_run_key

LOGDIR = ROOT / "runs" / "agentdojo_upstream"
DEFAULT_PROGRESS = ROOT / "runs" / "paper_m1_stress_progress.json"
DEFAULT_PROFILE = "m1_stress"
STRESS_DEFENSES = [
    "none",
    "spotlighting_with_delimiting",
    "repeat_user_prompt",
    "bio_idea1_provenance_reflection_meta_full",
]


def iter_stress_batches(profile: dict, model_modes: list[str]) -> list[tuple[str, str, str, str]]:
    suites = sorted({t["suite"] for t in profile["tasks"]})
    out: list[tuple[str, str, str, str]] = []
    for model in model_modes:
        for attack in profile["attacks"]:
            for inj in profile["injection_tasks"]:
                for suite in suites:
                    out.append((model, attack, inj, suite))
    return out


def summarize_batch(bench_dir: Path, *, profile: dict, model_mode: str, attack: str, injection_task: str) -> dict:
    rows = collect_live_from_benchmarks(
        [bench_dir],
        curated_tasks=profile["tasks"],
        model_mode=model_mode,
        attacks=[attack],
        injection_tasks=[injection_task],
    )
    by_def: dict[str, list[dict]] = {}
    for r in rows:
        by_def.setdefault(r["defense"], []).append(r)

    def rates(defense: str) -> dict[str, float | None]:
        items = by_def.get(defense) or []
        if not items:
            return {"utility": None, "security": None, "ASR": None, "n": 0}
        util = sum(bool(x["utility"]) for x in items) / len(items)
        sec = sum(bool(x["security"]) for x in items) / len(items)
        return {"utility": round(util, 4), "security": round(sec, 4), "ASR": round(1 - sec, 4), "n": len(items)}

    return {d: rates(d) for d in STRESS_DEFENSES if d in profile["defenses"] or d in by_def}


def run_batch(
    *,
    model_mode: str,
    attack: str,
    injection_task: str,
    suite: str,
    profile: dict,
    progress_path: Path,
    force_rerun: bool,
) -> Path:
    import eval.attacks.stress_attacks  # noqa: F401 — register persona attacks

    key = suite_run_key(model_mode, attack, injection_task, suite)
    progress = load_progress(progress_path)
    if not force_rerun and key in progress.get("completed", {}):
        return Path(progress["completed"][key]["run_dir"])

    tasks = [t["user_task"] for t in profile["tasks"] if t["suite"] == suite]
    actual_inj = resolve_injection_task_id(suite, injection_task)
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "eval" / "run_agentdojo_benchmark.py"),
        "--model-mode",
        model_mode,
        "--suite",
        suite,
        "--injection-task",
        actual_inj,
        "--attack",
        attack,
        "--logdir",
        str(LOGDIR),
    ]
    if force_rerun:
        cmd.append("--force-rerun")
    for ut in tasks:
        cmd.extend(["--user-task", ut])
    for defense in profile["defenses"]:
        cmd.extend(["--defense", defense])

    print(f"\n=== STRESS RUN {key} ===", flush=True)
    print(" ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"Stress benchmark failed rc={proc.returncode} for {key}")

    bench_dir = sorted(LOGDIR.glob("benchmark_*"), key=lambda p: p.stat().st_mtime, reverse=True)[0]
    summary = summarize_batch(
        bench_dir, profile=profile, model_mode=model_mode, attack=attack, injection_task=injection_task
    )
    progress.setdefault("completed", {})[key] = {
        "run_dir": str(bench_dir.resolve()),
        "returncode": proc.returncode,
        "summary": summary,
    }
    save_progress(progress_path, progress)
    print(json.dumps(summary, indent=2), flush=True)
    return bench_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress-file", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Curated profile name (m1_stress, m1_banking_stress)")
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument("--model-mode", default="deepseek")
    parser.add_argument("--attack", default=None, help="Run only this attack variant")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    profile = load_curated_profile(args.profile)
    if args.progress_file == DEFAULT_PROGRESS and args.profile == "m1_banking_stress":
        args.progress_file = ROOT / "runs" / "paper_m1_banking_stress_progress.json"
    attacks = [args.attack] if args.attack else profile["attacks"]
    profile = dict(profile)
    profile["attacks"] = attacks

    batches = iter_stress_batches(profile, [args.model_mode])
    print(f"M1 stress ({args.profile}): {len(batches)} batches, progress={args.progress_file}", flush=True)

    for model, attack, inj, suite in batches:
        key = suite_run_key(model, attack, inj, suite)
        if args.dry_run:
            print(f"would run {key}")
            continue
        run_batch(
            model_mode=model,
            attack=attack,
            injection_task=inj,
            suite=suite,
            profile=profile,
            progress_path=args.progress_file,
            force_rerun=args.force_rerun,
        )

    print("\nStress slice complete.", flush=True)
    print(
        "Depth analysis example:\n"
        "  .venv/bin/python eval/analyze_injection_depth.py \\\n"
        "    --log-glob 'runs/agentdojo_upstream/benchmark_*/logs/*/spotlighting_with_delimiting/slack/**/*.json' \\\n"
        "    --defense spotlighting_with_delimiting --out runs/m1_stress_depth_spotlighting.json",
        flush=True,
    )


if __name__ == "__main__":
    main()
