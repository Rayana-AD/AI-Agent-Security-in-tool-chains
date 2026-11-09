#!/usr/bin/env python3
"""P1 L3: AutoDojo adaptive attack — optimize injections then compare static vs adaptive ASR.

Reasonable default scale (not rebuttal-max):
  banking · 1 injection_task · 2 user_tasks · 3 optimizer iterations · 2 defenses (none, bio_04)
"""

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

from eval.supplement.bootstrap_env import ensure_venv_python, env_for_autodojo, git_head, repo_root

ensure_venv_python()

DEFAULT_EXPERIMENT_ID = "adaptive_l3_v1"
AUTODOJO_ROOT = repo_root() / "third_party" / "AutoDojo"
OPTIMIZE_SCRIPT = AUTODOJO_ROOT / "agentdojo" / "variant_generation" / "optimize_variants.py"

# Deliberately modest: enough iterations to see adaptation, not a full-suite sweep.
# optimize_variants.py only supports banking/travel/slack/shopping/github/dailylife (not workspace).
DEFAULT_SUITE = "banking"
DEFAULT_INJECTION_TASKS = ("injection_task_0",)
DEFAULT_USER_TASKS = ("user_task_0", "user_task_1")
DEFAULT_ITERATIONS = 3
DEFAULT_N_VARIANTS = 2
DEFAULT_DEFENSES = ("no_defense", "bio_04")
DEFAULT_TARGET_MODEL = "deepseek/deepseek-chat"
DEFAULT_OPTIMIZER_MODEL = "deepseek-chat"


def env_for_optimizer(out_variants: Path) -> dict:
    env = env_for_autodojo()
    vg = AUTODOJO_ROOT / "agentdojo" / "variant_generation"
    src = AUTODOJO_ROOT / "agentdojo" / "src"
    parts = [str(vg), str(src), str(repo_root() / "src"), str(repo_root())]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*parts, existing] if existing else parts)
    env["AUTODOJO_OUTPUT_DIR"] = str(out_variants)
    nltk_data = repo_root() / ".venv" / "nltk_data"
    if nltk_data.is_dir():
        env["NLTK_DATA"] = str(nltk_data)
    return env


def _defense_cli(defense: str) -> list[str]:
    if defense in ("no_defense", "none", ""):
        return []
    return ["--defense", defense, "--run-defense"]


def _run_logged(cmd: list[str], env: dict, cwd: Path, log_path: Path) -> subprocess.CompletedProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(env)
    env["PYTHONUNBUFFERED"] = "1"
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write(" ".join(cmd) + "\n\n")
        fh.flush()
        proc = subprocess.run(cmd, env=env, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT, text=True)
    return proc


def _tail(path: Path, n: int = 1800) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-n:]


def run_optimize(
    *,
    suite: str,
    defense: str,
    target_model: str,
    optimizer_model: str,
    iterations: int,
    n_variants: int,
    injection_tasks: tuple[str, ...],
    user_tasks: tuple[str, ...],
    out_variants: Path,
    dry_run: bool,
    log_dir: Path | None = None,
) -> dict:
    env = env_for_optimizer(out_variants)
    cmd = [
        sys.executable,
        str(OPTIMIZE_SCRIPT),
        "--suite",
        suite,
        "--iterations",
        str(iterations),
        "--n-variants",
        str(n_variants),
        "--target-model",
        target_model,
        "--model",
        optimizer_model,
        "--provider",
        "deepseek",
        "--seed-styles",
        *_defense_cli(defense),
    ]
    for ut in user_tasks:
        cmd.extend(["--user-tasks", ut])
    for it in injection_tasks:
        cmd.extend(["--injection-tasks", it])
    # AutoDojo --dry-run still runs --eval-asr episodes (reachability + seed ASR) → real API cost.
    if not dry_run:
        cmd.append("--eval-asr")
    if dry_run:
        cmd.append("--dry-run")

    defense_key = defense if defense not in ("no_defense", "none", "") else "no_defense"
    cache_path = out_variants / suite / target_model / defense_key / "injections.json"
    log_path = (log_dir or out_variants.parent / "logs") / f"optimize_{defense_key}.log"
    proc = _run_logged(cmd, env, AUTODOJO_ROOT, log_path)
    return {
        "phase": "optimize",
        "defense": defense_key,
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "cache_path": str(cache_path),
        "cache_exists": cache_path.exists(),
        "log_path": str(log_path),
        "stdout_tail": _tail(log_path),
    }


def run_benchmark(
    *,
    suite: str,
    defense: str,
    attack: str,
    target_model: str,
    injection_tasks: tuple[str, ...],
    user_tasks: tuple[str, ...],
    logdir: Path,
    cache_path: Path | None,
    dry_run: bool,
    cmd_log_dir: Path | None = None,
) -> dict:
    env = env_for_autodojo()
    if cache_path is not None:
        env["AUTODOJO_CACHE"] = str(cache_path)
    cmd = [
        sys.executable,
        "-m",
        "agentdojo.scripts.benchmark",
        "--model",
        target_model,
        "--suite",
        suite,
        "--attack",
        attack,
        "--logdir",
        str(logdir),
        "--force-rerun",
    ]
    dkey = defense if defense not in ("no_defense", "none", "") else "no_defense"
    if dkey != "no_defense":
        cmd.extend(["--defense", defense])
    for ut in user_tasks:
        cmd.extend(["-ut", ut])
    for it in injection_tasks:
        cmd.extend(["-it", it])
    if dry_run:
        return {"phase": "benchmark", "attack": attack, "defense": dkey, "command": " ".join(cmd), "dry_run": True}

    log_path = (cmd_log_dir or logdir.parent / "logs") / f"bench_{dkey}_{attack}.log"
    proc = _run_logged(cmd, env, AUTODOJO_ROOT, log_path)
    return {
        "phase": "benchmark",
        "attack": attack,
        "defense": dkey,
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "log_path": str(log_path),
        "stdout_tail": _tail(log_path, 1200),
    }


def _aggregate_benchmark_log(logdir: Path, defense: str, suite: str, attack: str | None = None) -> dict:
    """ASR/utility from AgentDojo episode JSON.

    In these logs ``security=true`` means the injection goal succeeded (ASR),
    not defense-side security. Defense security is ``1 - ASR``.
    """
    dkey = defense if defense != "no_defense" else "no_defense"
    inj_logs = sorted(logdir.glob(f"**/{dkey}/{suite}/**/injection_task_*.json"))
    if attack:
        inj_logs = [p for p in inj_logs if f"/{attack}/" in str(p).replace("\\", "/")]
    if not inj_logs:
        return {"n_logs": 0}
    util = []
    hijack = []
    for p in inj_logs:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "utility" in data:
            util.append(float(data["utility"]))
        if "security" in data:
            hijack.append(float(data["security"]))
    asr = (sum(hijack) / len(hijack)) if hijack else None
    return {
        "n_logs": len(inj_logs),
        "utility_mean": round(sum(util) / len(util), 4) if util else None,
        "asr_mean": round(asr, 4) if asr is not None else None,
        "defense_security_mean": round(1.0 - asr, 4) if asr is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDojo L3 adaptive (reasonable scale)")
    parser.add_argument("--execute", action="store_true", help="Run optimize + benchmark (needs API)")
    parser.add_argument("--optimize-only", action="store_true")
    parser.add_argument("--benchmark-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print plan / dry-run optimize only")
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--n-variants", type=int, default=DEFAULT_N_VARIANTS)
    parser.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    parser.add_argument("--optimizer-model", default=DEFAULT_OPTIMIZER_MODEL)
    parser.add_argument("--defenses", nargs="+", default=list(DEFAULT_DEFENSES))
    parser.add_argument("--injection-tasks", nargs="+", default=list(DEFAULT_INJECTION_TASKS))
    parser.add_argument("--user-tasks", nargs="+", default=list(DEFAULT_USER_TASKS))
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--experiment-id", default=DEFAULT_EXPERIMENT_ID)
    parser.add_argument("--skip-existing", action="store_true", help="Skip optimize if injections.json already exists")
    args = parser.parse_args()

    from eval.supplement.results_store import SupplementRunStore

    store = SupplementRunStore(args.out_root)
    experiment_id = args.experiment_id
    exp_dir = store.experiment_dir("p1", experiment_id)
    variants_dir = exp_dir / "variants"
    bench_logdir = exp_dir / "benchmark_logs"
    cmd_log_dir = exp_dir / "logs"

    plan = {
        "experiment_id": experiment_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "autodojo_commit": git_head(AUTODOJO_ROOT),
        "python": sys.version,
        "scale": {
            "suite": args.suite,
            "injection_tasks": args.injection_tasks,
            "user_tasks": args.user_tasks,
            "iterations": args.iterations,
            "n_variants": args.n_variants,
            "defenses": args.defenses,
            "target_model": args.target_model,
            "optimizer_model": args.optimizer_model,
            "estimated_optimizer_cells": len(args.defenses) * len(args.injection_tasks) * args.iterations,
        },
        "threat_model": "L3 black-box: optimizer iterates on injection text; --run-defense applies defense during ASR eval",
        "runs": [],
        "comparison": {},
        "status": "planned",
    }

    do_opt = not args.benchmark_only
    do_bench = not args.optimize_only

    if args.execute or args.dry_run:
        variants_dir.mkdir(parents=True, exist_ok=True)
        caches: dict[str, Path] = {}

        if do_opt:
            for defense in args.defenses:
                dkey = defense if defense not in ("no_defense", "none", "") else "no_defense"
                cache_path = variants_dir / args.suite / args.target_model / dkey / "injections.json"
                if args.skip_existing and cache_path.exists():
                    rec = {
                        "phase": "optimize",
                        "defense": dkey,
                        "skipped": "cache exists",
                        "cache_path": str(cache_path),
                        "cache_exists": True,
                        "returncode": 0,
                    }
                else:
                    rec = run_optimize(
                        suite=args.suite,
                        defense=defense,
                        target_model=args.target_model,
                        optimizer_model=args.optimizer_model,
                        iterations=args.iterations,
                        n_variants=args.n_variants,
                        injection_tasks=tuple(args.injection_tasks),
                        user_tasks=tuple(args.user_tasks),
                        out_variants=variants_dir,
                        dry_run=args.dry_run,
                        log_dir=cmd_log_dir,
                    )
                plan["runs"].append(rec)
                plan["status"] = "running"
                store.write_json("p1", experiment_id, "report.json", plan)
                if rec.get("cache_exists"):
                    caches[rec["defense"]] = Path(rec["cache_path"])

        if do_bench and args.execute and not args.dry_run:
            for defense in args.defenses:
                dkey = defense if defense not in ("no_defense", "none") else "no_defense"
                cache = caches.get(dkey) or (
                    variants_dir / args.suite / args.target_model / dkey / "injections.json"
                )
                for attack in ("important_instructions", "autodojo"):
                    if attack == "autodojo" and not cache.exists():
                        plan["runs"].append(
                            {"phase": "benchmark", "attack": attack, "defense": dkey, "skipped": "no cache"}
                        )
                        continue
                    rec = run_benchmark(
                        suite=args.suite,
                        defense=defense,
                        attack=attack,
                        target_model=args.target_model,
                        injection_tasks=tuple(args.injection_tasks),
                        user_tasks=tuple(args.user_tasks),
                        logdir=bench_logdir,
                        cache_path=cache if attack == "autodojo" else None,
                        dry_run=False,
                        cmd_log_dir=cmd_log_dir,
                    )
                    rec["metrics"] = _aggregate_benchmark_log(bench_logdir, dkey, args.suite, attack)
                    plan["runs"].append(rec)

        failed = [r for r in plan["runs"] if r.get("returncode", 0) != 0 and not r.get("dry_run")]
        plan["status"] = "ok" if not failed else "partial_fail" if plan["runs"] else "planned"

        # Static vs adaptive gap per defense
        for defense in args.defenses:
            dkey = defense if defense not in ("no_defense", "none") else "no_defense"
            static = next(
                (r for r in plan["runs"] if r.get("attack") == "important_instructions" and r.get("defense") == dkey),
                {},
            )
            adaptive = next(
                (r for r in plan["runs"] if r.get("attack") == "autodojo" and r.get("defense") == dkey),
                {},
            )
            plan["comparison"][dkey] = {
                "static_asr": (static.get("metrics") or {}).get("asr_mean"),
                "adaptive_asr": (adaptive.get("metrics") or {}).get("asr_mean"),
                "delta_asr": None,
            }
            s, a = plan["comparison"][dkey]["static_asr"], plan["comparison"][dkey]["adaptive_asr"]
            if s is not None and a is not None:
                plan["comparison"][dkey]["delta_asr"] = round(a - s, 4)

    store.write_json("p1", experiment_id, "report.json", plan)
    print(json.dumps(plan, indent=2))
    print(f"\nP1 adaptive L3 → {exp_dir}")
    if plan.get("status") == "partial_fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
