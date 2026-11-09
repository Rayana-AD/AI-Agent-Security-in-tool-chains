#!/usr/bin/env python3
"""Run full AgentDojo upstream benchmark: paper defenses vs BioHarness Idea1/Idea2."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Prefer the AutoDojo agentdojo checkout over the ipiguard fork that may be
# installed in the venv; the two are not API-compatible for our benchmark.
sys.path.insert(0, str(ROOT / "third_party" / "AutoDojo" / "agentdojo" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

try:
    import eval.attacks.stress_attacks  # noqa: F401 — register persona/education attacks
except ImportError:
    pass

import yaml
from agentdojo.attacks.attack_registry import load_attack
from agentdojo.benchmark import benchmark_suite_with_injections, benchmark_suite_without_injections
from agentdojo.logging import OutputLogger
from agentdojo.task_suite.load_suites import get_suite, get_suites
from tqdm import tqdm

from bio_harness.config import CONFIGS_DIR
from eval.agentdojo.pipeline_factory import (
    BIO_DEFENSES,
    PAPER_DEFENSES,
    build_pipeline,
    resolve_llm,
)


def load_agentdojo_config() -> dict:
    path = CONFIGS_DIR / "agentdojo.yaml"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def aggregate_suite_results(result: dict) -> dict:
    util = list(result["utility_results"].values())
    # AgentDojo injection tasks return True when the injection goal succeeds.
    # Report that as ASR, and derive defense security as 1 - ASR.
    attack_success = list(result["security_results"].values())
    asr = sum(attack_success) / max(len(attack_success), 1)
    return {
        "utility": round(sum(util) / max(len(util), 1), 4),
        "security": round(1 - asr, 4),
        "ASR": round(asr, 4),
        "n_pairs": len(util),
        "utility_pct": round(100 * sum(util) / max(len(util), 1), 2),
        "security_pct": round(100 * (1 - asr), 2),
        "ASR_pct": round(100 * asr, 2),
    }


def combined_from_results(defense_results: dict) -> dict:
    util: list[float] = []
    sec: list[float] = []
    asr: list[float] = []
    for metrics in defense_results.values():
        if not isinstance(metrics, dict) or "error" in metrics or "utility" not in metrics:
            continue
        util.append(metrics["utility"])
        sec.append(metrics["security"])
        asr.append(metrics.get("ASR", 1 - metrics["security"]))
    if not util:
        return {"error": "no successful suites"}
    return {
        "avg_utility": round(sum(util) / len(util), 4),
        "avg_security": round(sum(sec) / len(sec), 4),
        "avg_utility_pct": round(100 * sum(util) / len(util), 2),
        "avg_security_pct": round(100 * sum(sec) / len(sec), 2),
        "ASR": round(sum(asr) / len(asr), 4),
        "ASR_pct": round(100 * sum(asr) / len(asr), 2),
    }


def run_defense_on_suite(
    defense: str,
    suite_name: str,
    *,
    llm,
    llm_name: str,
    provider: str,
    attack: str | None,
    benchmark_version: str,
    logdir: Path,
    force_rerun: bool,
    user_tasks: tuple[str, ...],
    injection_tasks: tuple[str, ...] = (),
) -> dict:
    suite = get_suite(benchmark_version, suite_name)
    pipeline = build_pipeline(defense, llm, llm_name, provider=provider)
    t0 = time.perf_counter()
    log_path = logdir / defense / suite_name
    log_path.mkdir(parents=True, exist_ok=True)

    n_user = len(user_tasks) if user_tasks else len(suite.user_tasks)
    n_inj = len(injection_tasks) if injection_tasks else len(suite.injection_tasks)
    print(
        f"  [{defense}/{suite_name}] pipeline={pipeline.name} "
        f"user_tasks≈{n_user} injection_tasks≈{n_inj}",
        flush=True,
    )

    with OutputLogger(str(log_path)):
        if attack is None:
            results = benchmark_suite_without_injections(
                pipeline,
                suite,
                user_tasks=user_tasks or None,
                logdir=log_path,
                force_rerun=force_rerun,
                benchmark_version=benchmark_version,
            )
        else:
            attacker = load_attack(attack, suite, pipeline)
            results = benchmark_suite_with_injections(
                pipeline,
                suite,
                attacker,
                user_tasks=user_tasks or None,
                injection_tasks=injection_tasks or None,
                logdir=log_path,
                force_rerun=force_rerun,
                benchmark_version=benchmark_version,
            )

    metrics = aggregate_suite_results(results)
    metrics["latency_seconds"] = round(time.perf_counter() - t0, 2)
    metrics["pipeline_name"] = pipeline.name
    return metrics


def _wait_for_process(pid: int, *, poll_seconds: float = 30.0) -> None:
    """Block until *pid* is no longer running."""
    import os

    print(f"Waiting for PID {pid} to finish before starting benchmark...", flush=True)
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            print(f"PID {pid} exited; starting benchmark.", flush=True)
            return
        time.sleep(poll_seconds)


def main() -> None:
    cfg = load_agentdojo_config()
    parser = argparse.ArgumentParser(description="AgentDojo upstream benchmark")
    parser.add_argument("--benchmark-version", default=cfg.get("benchmark_version", "v1.2.2"))
    parser.add_argument(
        "--attack",
        action="append",
        dest="attacks",
        help="Injection attack(s); repeat for multiple. Default: configs/agentdojo.yaml attacks list",
    )
    parser.add_argument("--model-mode", default=cfg.get("model_mode", "hf"))
    parser.add_argument("--model-id", default=cfg.get("model_id"))
    parser.add_argument("--suite", "-s", action="append", dest="suites")
    parser.add_argument("--defense", "-d", action="append", dest="defenses")
    parser.add_argument("--user-task", "-ut", action="append", dest="user_tasks", default=[])
    parser.add_argument("--injection-task", "-it", action="append", dest="injection_tasks", default=[])
    parser.add_argument("--logdir", type=Path, default=Path(cfg.get("logdir", "runs/agentdojo_upstream")))
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Continue in an existing benchmark_* directory (reuses cached logs)",
    )
    parser.add_argument("--force-rerun", "-f", action="store_true")
    parser.add_argument("--benign-only", action="store_true", help="Run without attack (utility only)")
    parser.add_argument("--skip-tool-filter", action="store_true", help="Omit tool_filter defense from run")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Quick smoke: workspace, user_task_0, 2 injection tasks, none+bio_full",
    )
    parser.add_argument(
        "--wait-pid",
        type=int,
        default=None,
        help="Wait for this process ID to exit before running (chain benchmarks)",
    )
    args = parser.parse_args()

    if args.wait_pid:
        _wait_for_process(args.wait_pid)

    if args.smoke:
        args.suites = args.suites or ["workspace"]
        args.defenses = args.defenses or ["none", "bio_full"]
        args.user_tasks = args.user_tasks or ["user_task_0"]
        args.injection_tasks = args.injection_tasks or ["injection_task_0", "injection_task_1"]

    suites = args.suites or cfg.get("suites") or list(get_suites(args.benchmark_version).keys())
    paper = [d for d in (args.defenses or cfg.get("paper_defenses") or PAPER_DEFENSES) if d in PAPER_DEFENSES or d == "none"]
    bio = args.defenses or cfg.get("bio_defenses") or list(BIO_DEFENSES.keys())
    if args.defenses:
        paper = [d for d in args.defenses if d in PAPER_DEFENSES or d == "none"]
        bio = [d for d in args.defenses if d in BIO_DEFENSES]
    defenses = paper + bio
    if args.skip_tool_filter:
        defenses = [d for d in defenses if d != "tool_filter"]

    attacks: list[str | None]
    if args.benign_only:
        attacks = [None]
    elif args.attacks:
        attacks = list(dict.fromkeys(args.attacks))
    else:
        attacks = list(dict.fromkeys(cfg.get("attacks") or [cfg.get("attack", "tool_knowledge")]))

    priority = cfg.get("model_priority")
    print(f"Resolving LLM (mode={args.model_mode})...", flush=True)
    llm, llm_name, provider = resolve_llm(
        args.model_mode, args.model_id, model_priority=priority
    )
    print(f"Using provider={provider} model={llm_name}", flush=True)

    user_tasks = tuple(args.user_tasks)
    injection_tasks = tuple(args.injection_tasks)

    if args.run_dir:
        out_dir = args.run_dir.resolve()
        if not out_dir.is_dir():
            raise SystemExit(f"--run-dir not found: {out_dir}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = args.logdir / f"benchmark_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "report.json"
    if args.run_dir and report_path.exists():
        with report_path.open(encoding="utf-8") as f:
            report = json.load(f)
        report.setdefault("results", {})
        report.setdefault("combined", {})
    else:
        report = {
            "benchmark_version": args.benchmark_version,
            "attacks": [a for a in attacks if a is not None],
            "attack": attacks[0] if attacks and attacks[0] else None,
            "model_mode": args.model_mode,
            "provider": provider,
            "model_name": llm_name,
            "suites": suites,
            "defenses": defenses,
            "results": {},
            "results_by_attack": {},
            "combined": {},
            "combined_by_attack": {},
        }

    report["benchmark_version"] = args.benchmark_version
    report["attacks"] = [a for a in attacks if a is not None]
    report["attack"] = attacks[0] if attacks and attacks[0] else None
    report["model_mode"] = args.model_mode
    report["provider"] = provider
    report["model_name"] = llm_name
    all_defenses = list(dict.fromkeys([*(report.get("defenses") or []), *defenses]))
    report["defenses"] = all_defenses
    report.setdefault("results_by_attack", {})
    report.setdefault("combined_by_attack", {})

    for attack in attacks:
        attack_key = attack or "benign_only"
        report["results_by_attack"].setdefault(attack_key, {})
        report["combined_by_attack"].setdefault(attack_key, {})
        # Legacy top-level results mirror primary attack for backward compatibility
        if attack == attacks[0]:
            report.setdefault("results", report["results_by_attack"][attack_key])
            report.setdefault("combined", report["combined_by_attack"][attack_key])

        print(f"\n=== Attack: {attack_key} ===", flush=True)
        for defense in defenses:
            report["results_by_attack"][attack_key].setdefault(defense, {})
            for suite_name in tqdm(suites, desc=f"{attack_key}/{defense}"):
                metrics: dict = {}
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        metrics = run_defense_on_suite(
                            defense,
                            suite_name,
                            llm=llm,
                            llm_name=llm_name,
                            provider=provider,
                            attack=attack,
                            benchmark_version=args.benchmark_version,
                            logdir=out_dir / "logs" / attack_key,
                            force_rerun=args.force_rerun and attempt == 0,
                            user_tasks=user_tasks,
                            injection_tasks=injection_tasks,
                        )
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        if "Connection error" in str(e) and attempt < 2:
                            wait_s = 30 * (attempt + 1)
                            print(
                                f"  [{defense}/{suite_name}] connection error, retry in {wait_s}s "
                                f"(attempt {attempt + 1}/3)",
                                flush=True,
                            )
                            time.sleep(wait_s)
                            continue
                        metrics = {"error": str(e), "utility": 0.0, "security": 0.0}
                        break
                if last_error and "error" not in metrics:
                    metrics = {"error": str(last_error), "utility": 0.0, "security": 0.0}
                report["results_by_attack"][attack_key][defense][suite_name] = metrics

        report["combined_by_attack"][attack_key] = combined_from_results(
            report["results_by_attack"][attack_key]
        )
        if attack == attacks[0]:
            report["results"] = report["results_by_attack"][attack_key]
            report["combined"] = report["combined_by_attack"][attack_key]
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  checkpoint saved → {report_path}", flush=True)

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n=== AgentDojo Benchmark Summary ===")
    print(f"Model: {llm_name} | Attacks: {report['attacks']} | Version: {args.benchmark_version}")
    print(f"Report: {report_path}\n")
    header = f"{'Attack':<22} {'Defense':<24} {'Utility':>10} {'Security':>10} {'ASR':>8}"
    print(header)
    print("-" * len(header))
    for attack_key, combined_map in report.get("combined_by_attack", {}).items():
        for defense in all_defenses:
            c = combined_map.get(defense, {})
            if not c or "error" in c:
                continue
            print(
                f"{attack_key:<22} {defense:<24} {c['avg_utility_pct']:>9.1f}% "
                f"{c['avg_security_pct']:>9.1f}% {c['ASR']*100:>7.1f}%"
            )


if __name__ == "__main__":
    main()
