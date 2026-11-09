#!/usr/bin/env python3
"""Paper experiment suite: offline probes, M1 curated live, M2 metrics."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.paper_curated import load_curated_profile, logical_injection_task_id, resolve_injection_task_id, scale_check
from eval.paper_mechanism import scan_logdir
from eval.paper_metrics import (
    cross_model_comparison,
    frontier_dominance,
    hypervolume_by_group,
    module_delta_vs_full,
    paired_task_metrics,
)
from eval.paper_probe import (
    IDEA1_DECOMPOSITION,
    MODULE_ABLATIONS,
    SCHEME_PROGRESSION,
    module_failure_delta,
    probe_scheme,
    run_multi_task_offline,
    security_score_from_row,
    utility_score_from_row,
)

DEFAULT_SECOND_MODEL = "openrouter_llama70"
DEFAULT_PROGRESS_FILE = ROOT / "runs" / "paper_m1_live_progress.json"


def suite_run_key(model_mode: str, attack: str, injection_task: str, suite: str) -> str:
    return f"{model_mode}|{attack}|{injection_task}|{suite}"


def load_progress(path: Path) -> dict:
    if not path.exists():
        return {"completed": {}, "active": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"completed": {}, "active": {}}
    data.setdefault("completed", {})
    data.setdefault("active", {})
    return data


def save_progress(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def resolve_curated_defenses(*, p1_baselines: bool, p2_baselines: bool) -> list[str]:
    """Legacy flags when --profile is not used."""
    p0 = [
        "none",
        "tool_filter",
        "bio_idea1_provenance_reflection_meta_full",
    ]
    if p2_baselines:
        return p0 + [
            "spotlighting_with_delimiting",
            "repeat_user_prompt",
            "transformers_pi_detector",
        ]
    if p1_baselines:
        return p0 + ["spotlighting_with_delimiting", "repeat_user_prompt"]
    return p0


def _metric_rows(live_rows: list[dict]) -> list[dict]:
    return [
        {
            "defense": r["defense"],
            "suite": r.get("suite"),
            "user_task": r.get("user_task"),
            "attack": r.get("attack"),
            "injection_task": r.get("injection_task"),
            "replicate": r.get("replicate"),
            "utility": 1.0 if r["utility"] else 0.0,
            "security": 1.0 if r["security"] else 0.0,
        }
        for r in live_rows
    ]


def _build_live_block(live_rows: list[dict], defenses: list[str], profile: dict) -> dict:
    metric_input = _metric_rows(live_rows)
    n_tasks = len({(r["suite"], r["user_task"]) for r in live_rows})
    n_pairs = len(live_rows)
    return {
        "paired_rows": live_rows,
        "paired_metrics": paired_task_metrics(metric_input),
        "frontier": frontier_dominance(metric_input),
        "n_tasks": n_tasks,
        "n_defenses": len({r["defense"] for r in live_rows}),
        "n_rows": n_pairs,
        "n_pairs": n_pairs,
        "defenses": defenses,
        "suites": sorted({r["suite"] for r in live_rows}),
        "attacks": profile.get("attacks"),
        "injection_tasks": profile.get("injection_tasks"),
        "scale_check": scale_check(profile),
    }


def run_offline() -> dict:
    scheme_rows = []
    for scheme_id, stage, config_key in SCHEME_PROGRESSION:
        row = probe_scheme(config_key, scheme_id=scheme_id, stage=stage)
        row["utility_score"] = utility_score_from_row(row)
        row["security_score"] = security_score_from_row(row)
        scheme_rows.append(row)

    module_rows = []
    for scheme_id, config_key in MODULE_ABLATIONS:
        row = probe_scheme(config_key, scheme_id=scheme_id, stage="module_ablation")
        row["utility_score"] = utility_score_from_row(row)
        row["security_score"] = security_score_from_row(row)
        module_rows.append(row)

    idea_rows = []
    for scheme_id, config_key in IDEA1_DECOMPOSITION:
        row = probe_scheme(config_key, scheme_id=scheme_id, stage="idea1_decomposition")
        row["utility_score"] = utility_score_from_row(row)
        row["security_score"] = security_score_from_row(row)
        idea_rows.append(row)

    multi_task_rows = run_multi_task_offline("idea1_provenance_mlp_refl_meta_full", scheme_id="E6_meta_full")
    module_deltas = module_delta_vs_full(module_rows)

    return {
        "scheme_progression": scheme_rows,
        "module_ablation": module_rows,
        "module_delta_vs_full": module_deltas,
        "module_failure_impact": module_failure_delta(module_rows, module_deltas),
        "idea1_decomposition": idea_rows,
        "multi_task_fixtures": multi_task_rows,
        "multi_task_summary": {
            "mean_utility": sum(r["utility_score"] for r in multi_task_rows) / len(multi_task_rows),
            "mean_security": sum(r["security_score"] for r in multi_task_rows) / len(multi_task_rows),
            "by_task_type": {r["task_type"]: r["utility_score"] for r in multi_task_rows},
        },
        "hypervolume": {
            "scheme_progression": hypervolume_by_group(scheme_rows, "stage"),
            "module_ablation": hypervolume_by_group(module_rows, "stage"),
        },
    }


def _benchmark_meta(bdir: Path) -> dict:
    report_path = bdir / "report.json"
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def collect_live_from_benchmarks(
    benchmark_dirs: list[Path],
    *,
    curated_tasks: list[dict],
    model_mode: str = "deepseek",
    attacks: list[str] | None = None,
    injection_tasks: list[str] | None = None,
) -> list[dict]:
    """Merge per-task rows from AgentDojo benchmark log trees."""
    attacks_set = set(attacks or [])
    injections_set = set(injection_tasks or [])
    task_lookup = {(t["suite"], t["user_task"]): t for t in curated_tasks}
    rows: dict[tuple[str, ...], dict] = {}

    for bdir in benchmark_dirs:
        if not bdir.exists():
            continue
        bench_meta = _benchmark_meta(bdir)
        if model_mode and bench_meta.get("model_mode") not in (None, model_mode):
            continue
        bench_attacks = bench_meta.get("attacks") or ([bench_meta.get("attack")] if bench_meta.get("attack") else [])
        if attacks_set and bench_attacks and not attacks_set.intersection(bench_attacks):
            continue

        logs_root = bdir / "logs"
        if not logs_root.exists():
            continue
        mtime = bdir.stat().st_mtime

        for log_path in logs_root.glob("**/injection_task_*.json"):
            inj_name = log_path.stem
            parts = log_path.parts
            if "user_task_" not in str(log_path):
                continue
            try:
                ut_idx = next(i for i, p in enumerate(parts) if p.startswith("user_task_"))
                user_task = parts[ut_idx]
                suite = parts[ut_idx - 1] if ut_idx > 0 else ""
            except StopIteration:
                continue
            try:
                logical_inj = logical_injection_task_id(suite, inj_name)
            except ValueError:
                logical_inj = inj_name
            if injections_set and logical_inj not in injections_set and inj_name not in injections_set:
                continue
            if (suite, user_task) not in task_lookup:
                continue

            attack_key = "unknown"
            defense = "unknown"
            for i, p in enumerate(parts):
                if p == "logs" and i + 2 < len(parts):
                    attack_key = parts[i + 1]
                    defense = parts[i + 2]
                    break
            if attacks_set and attack_key not in attacks_set:
                continue

            key = (suite, user_task, defense, attack_key, logical_inj)
            prev = rows.get(key)
            if prev and prev.get("_mtime", 0) >= mtime:
                continue
            try:
                data = json.loads(log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            task_meta = task_lookup[(suite, user_task)]
            rows[key] = {
                "defense": defense,
                "suite": suite,
                "user_task": user_task,
                "task_type": task_meta["task_type"],
                "attack": attack_key,
                "injection_task": logical_inj,
                "utility": bool(data.get("utility", False)),
                "security": not bool(data.get("security", False)),
                "model_mode": bench_meta.get("model_mode") or model_mode,
                "log_path": str(log_path),
                "benchmark_dir": str(bdir),
                "_mtime": mtime,
            }

    out = list(rows.values())
    for row in out:
        row.pop("_mtime", None)
    return out


def run_curated_live(
    *,
    profile: dict,
    model_mode: str,
    logdir: Path,
    replicate: int = 0,
    progress_path: Path | None = None,
    force_rerun: bool = False,
) -> dict:
    """Run curated tasks: suites × attacks × injections (one benchmark per combo)."""
    curated_tasks: list[dict] = profile["tasks"]
    defenses: list[str] = profile["defenses"]
    attacks: list[str] = profile["attacks"]
    injection_tasks: list[str] = profile["injection_tasks"]
    progress_file = progress_path or DEFAULT_PROGRESS_FILE
    progress = load_progress(progress_file)

    reports = []
    run_benchmark_dirs: list[Path] = []
    suites = sorted({t["suite"] for t in curated_tasks})

    total_runs = len(suites) * len(attacks) * len(injection_tasks)
    run_idx = 0
    for attack in attacks:
        for injection_task in injection_tasks:
            for suite in suites:
                run_idx += 1
                key = suite_run_key(model_mode, attack, injection_task, suite)
                tasks = [t["user_task"] for t in curated_tasks if t["suite"] == suite]

                if not force_rerun and key in progress["completed"]:
                    done = progress["completed"][key]
                    bench_dir = Path(done["run_dir"])
                    print(
                        f"\n[{run_idx}/{total_runs}] SKIP (done) {key} → {bench_dir}",
                        flush=True,
                    )
                    if bench_dir.exists():
                        run_benchmark_dirs.append(bench_dir)
                    reports.append(
                        {
                            "suite": suite,
                            "attack": attack,
                            "injection_task": injection_task,
                            "skipped": True,
                            **done,
                        }
                    )
                    continue

                resume_dir: Path | None = None
                if not force_rerun:
                    active = progress.get("active", {}).get(key)
                    if active and active.get("run_dir"):
                        candidate = Path(active["run_dir"])
                        if candidate.is_dir():
                            resume_dir = candidate

                print(
                    f"\n[{run_idx}/{total_runs}] model={model_mode} attack={attack} "
                    f"inj={injection_task} suite={suite} tasks={len(tasks)} defenses={len(defenses)}"
                    + (f" resume={resume_dir.name}" if resume_dir else ""),
                    flush=True,
                )
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
                    str(logdir),
                ]
                if force_rerun:
                    cmd.append("--force-rerun")
                if resume_dir is not None:
                    cmd.extend(["--run-dir", str(resume_dir.resolve())])
                for ut in tasks:
                    cmd.extend(["--user-task", ut])
                for defense in defenses:
                    cmd.extend(["--defense", defense])

                proc = subprocess.run(cmd, cwd=ROOT)
                bench_dir: Path | None = resume_dir
                if proc.returncode != 0:
                    candidates = sorted(logdir.glob("benchmark_*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    bench_dir = candidates[0] if candidates else bench_dir
                    if bench_dir is not None:
                        progress.setdefault("active", {})[key] = {
                            "run_dir": str(bench_dir.resolve()),
                            "returncode": proc.returncode,
                        }
                        save_progress(progress_file, progress)
                    raise SystemExit(
                        f"Benchmark failed for {key} (rc={proc.returncode}). "
                        f"Progress saved → {progress_file}. Re-run the same command to resume."
                    )

                candidates = sorted(logdir.glob("benchmark_*"), key=lambda p: p.stat().st_mtime, reverse=True)
                bench_dir = resume_dir or (candidates[0] if candidates else None)
                if bench_dir is not None:
                    run_benchmark_dirs.append(bench_dir)
                    progress["completed"][key] = {
                        "run_dir": str(bench_dir.resolve()),
                        "returncode": proc.returncode,
                    }
                    progress.get("active", {}).pop(key, None)
                    save_progress(progress_file, progress)

                reports.append(
                    {
                        "suite": suite,
                        "attack": attack,
                        "injection_task": injection_task,
                        "tasks": tasks,
                        "defenses": defenses,
                        "returncode": proc.returncode,
                        "benchmark_dir": str(bench_dir) if bench_dir else "",
                    }
                )

    unique_dirs = list(dict.fromkeys(run_benchmark_dirs))
    live_rows = collect_live_from_benchmarks(
        unique_dirs,
        curated_tasks=curated_tasks,
        model_mode=model_mode,
        attacks=attacks,
        injection_tasks=injection_tasks,
    )
    live_rows = [r for r in live_rows if r["defense"] in defenses]
    if replicate:
        for row in live_rows:
            row["replicate"] = replicate

    block = _build_live_block(live_rows, defenses, profile)
    block.update(
        {
            "benchmark_dir": str(unique_dirs[0]) if unique_dirs else "",
            "benchmark_dirs": [str(p) for p in unique_dirs],
            "suite_runs": reports,
            "model_mode": model_mode,
            "replicate": replicate,
            "profile": profile.get("name"),
            "progress_file": str(progress_file),
        }
    )
    return block


def merge_mechanism(logdir: Path | None) -> dict:
    if logdir is None or not logdir.exists():
        return {"episodes": [], "by_mechanism": {}, "by_task_type": {}}
    episodes = scan_logdir(logdir)
    from collections import Counter

    mech_counter: Counter = Counter()
    task_mech: dict[str, Counter] = {}
    for ep in episodes:
        mech = ep.get("dominant_mechanism", "unknown")
        mech_counter[mech] += 1
        task_key = ep.get("user_task_id", "?")
        task_mech.setdefault(task_key, Counter())[mech] += 1
    return {
        "episodes": episodes,
        "by_mechanism": dict(mech_counter),
        "by_task_type": {k: dict(v) for k, v in task_mech.items()},
    }


def _merge_live_rows(
    bench_dirs: list[Path],
    *,
    profile: dict,
    model_mode: str,
    source: str,
) -> dict:
    defenses = profile["defenses"]
    live_rows = collect_live_from_benchmarks(
        bench_dirs,
        curated_tasks=profile["tasks"],
        model_mode=model_mode,
        attacks=profile["attacks"],
        injection_tasks=profile["injection_tasks"],
    )
    primary_rows = [r for r in live_rows if r["defense"] in defenses]
    metric_rows = primary_rows or live_rows
    block = _build_live_block(metric_rows, defenses, profile)
    block.update(
        {
            "source": source,
            "benchmark_dirs_scanned": len(bench_dirs),
            "paired_rows_all_defenses": live_rows,
            "model_mode": model_mode,
        }
    )
    return block


def _resolve_model_modes(args: argparse.Namespace, profile: dict) -> list[str]:
    modes: list[str] = []
    if args.model_modes:
        modes.extend(args.model_modes)
    elif args.model_mode:
        modes.append(args.model_mode)
    else:
        modes.extend(profile.get("model_modes") or ["deepseek"])
    if args.second_model and args.second_model not in modes:
        modes.append(args.second_model)
    return list(dict.fromkeys(modes))


def _resolve_profile(args: argparse.Namespace) -> dict:
    if args.profile:
        return load_curated_profile(args.profile)
    if args.m1_scale or (args.live and not args.offline_only):
        return load_curated_profile("m1")
    # Legacy merge/replot path
    tasks_profile = load_curated_profile("workshop")
    tasks_profile["defenses"] = resolve_curated_defenses(
        p1_baselines=args.p1_baselines,
        p2_baselines=args.p2_baselines,
    )
    if args.attacks:
        tasks_profile["attacks"] = list(args.attacks)
    elif args.attack:
        tasks_profile["attacks"] = [args.attack]
    if args.injection_tasks:
        tasks_profile["injection_tasks"] = list(args.injection_tasks)
    elif args.injection_task:
        tasks_profile["injection_tasks"] = [args.injection_task]
    return tasks_profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--skip-offline", action="store_true", help="Skip offline probes on --live")
    parser.add_argument("--live", action="store_true", help="Run curated live benchmark")
    parser.add_argument("--profile", choices=["m1", "workshop"], default=None, help="Curated scale profile")
    parser.add_argument("--m1-scale", action="store_true", help="Use M1 profile (50 tasks, 2×2×8)")
    parser.add_argument("--p1-baselines", action="store_true", help="Legacy: workshop + P1 baselines")
    parser.add_argument("--p2-baselines", action="store_true", help="Legacy: workshop + P2 baselines")
    parser.add_argument("--model-mode", default=None)
    parser.add_argument("--model-modes", nargs="+", default=None)
    parser.add_argument("--second-model", default=None)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--attacks", nargs="+", default=None)
    parser.add_argument("--attack", default=None, help="Legacy single attack")
    parser.add_argument("--injection-tasks", nargs="+", default=None)
    parser.add_argument("--injection-task", default=None, help="Legacy single injection")
    parser.add_argument("--logdir", type=Path, default=ROOT / "runs" / "agentdojo_upstream")
    parser.add_argument("--merge-logdir", type=Path, default=None)
    parser.add_argument("--merge-benchmarks", action="store_true")
    parser.add_argument("--replot-live-dirs", action="store_true")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=DEFAULT_PROGRESS_FILE,
        help="Checkpoint file for resume across suite runs",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore progress checkpoints and rerun all suite jobs",
    )
    args = parser.parse_args()

    profile = _resolve_profile(args)
    if args.attacks:
        profile = dict(profile)
        profile["attacks"] = list(args.attacks)
    if args.injection_tasks:
        profile = dict(profile)
        profile["injection_tasks"] = list(args.injection_tasks)
    replicates = args.replicates if args.replicates is not None else int(profile.get("replicates") or 1)

    model_modes = _resolve_model_modes(args, profile)
    if args.live and args.second_model is None and len(model_modes) == 1 and profile.get("name") == "m1":
        if DEFAULT_SECOND_MODEL not in model_modes:
            model_modes.append(DEFAULT_SECOND_MODEL)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "runs" / f"paper_suite_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    scale = scale_check(profile)
    print(f"M1 scale check: {json.dumps(scale, indent=2)}", flush=True)

    summary: dict = {
        "timestamp": ts,
        "profile": profile.get("name"),
        "curated_tasks": profile["tasks"],
        "curated_defenses": profile["defenses"],
        "attacks": profile["attacks"],
        "injection_tasks": profile["injection_tasks"],
        "model_modes": model_modes,
        "scale_check": scale,
    }
    if not args.skip_offline:
        summary["offline"] = run_offline()
    else:
        summary["offline"] = {"skipped": True}

    merge_path: Path | None = args.merge_logdir

    if args.live and not args.offline_only:
        live_by_model: dict[str, dict] = {}
        for mode in model_modes:
            rep_rows: list[dict] = []
            rep_blocks: list[dict] = []
            for rep in range(max(1, replicates)):
                block = run_curated_live(
                    profile=profile,
                    model_mode=mode,
                    logdir=args.logdir,
                    replicate=rep,
                    progress_path=args.progress_file,
                    force_rerun=args.force_rerun,
                )
                rep_blocks.append(block)
                rep_rows.extend(block.get("paired_rows") or [])
            if replicates > 1:
                merged = _build_live_block(rep_rows, profile["defenses"], profile)
                merged.update(
                    {
                        "model_mode": mode,
                        "replicates": replicates,
                        "replicate_blocks": rep_blocks,
                        "benchmark_dirs": [b for rb in rep_blocks for b in rb.get("benchmark_dirs") or []],
                    }
                )
                live_by_model[mode] = merged
            else:
                live_by_model[mode] = rep_blocks[0]
            if merge_path is None and live_by_model[mode].get("benchmark_dir"):
                merge_path = Path(live_by_model[mode]["benchmark_dir"])
        summary["live_by_model"] = live_by_model
        summary["live"] = live_by_model[model_modes[0]]
        summary["cross_model"] = cross_model_comparison(live_by_model)
    elif args.replot_live_dirs or args.merge_benchmarks or args.offline_only:
        bench_dirs = sorted(args.logdir.glob("benchmark_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        live_by_model = {}
        for mode in model_modes:
            live_by_model[mode] = _merge_live_rows(
                bench_dirs,
                profile=profile,
                model_mode=mode,
                source="merged_benchmarks" if args.merge_benchmarks else "replot_from_benchmark_dirs",
            )
        summary["live_by_model"] = live_by_model
        summary["live"] = live_by_model.get(model_modes[0]) or next(iter(live_by_model.values()), {})
        summary["cross_model"] = cross_model_comparison(live_by_model) if len(live_by_model) > 1 else {}
        merge_path = bench_dirs[0] if bench_dirs else args.merge_logdir
    else:
        merge_path = args.merge_logdir

    summary["mechanism"] = merge_mechanism(merge_path if merge_path and merge_path.exists() else None)

    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("mechanism", "offline", "curated_tasks")}, indent=2)[:6000])
    print(f"\nWrote {out_path}")

    if args.plot or args.live:
        plot_cmd = [
            sys.executable,
            str(ROOT / "eval" / "plot_paper_figures.py"),
            "--summary",
            str(out_path),
            "--out",
            str(out_dir / "figures"),
        ]
        if merge_path and merge_path.exists():
            plot_cmd.extend(["--logdir", str(merge_path)])
        subprocess.run(plot_cmd, cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
