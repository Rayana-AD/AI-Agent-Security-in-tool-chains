#!/usr/bin/env python3
"""Discover usable attack samples from cached AgentDojo logs and scripted harness.

Outputs ``runs/stress_manifest.json`` with:
- ``none_usable``: per-task cells where defense=none allows injection success
- ``spotlight_gaps``: same cells where spotlight also fails (security < 100%)
- ``bio_04_wins``: none allows attack but bio_04 blocks
- ``scripted_usable``: attack samples that succeed under baseline (no harness)
- ``scripted_bio_04_wins``: baseline ASR but bio_04 blocks

Usage:
  python eval/run_stress_manifest.py --scan-only
  python eval/run_stress_manifest.py --scripted
  python eval/run_stress_manifest.py --live-none --profile m1_none_sweep
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUTPUT = ROOT / "runs" / "stress_manifest.json"
DEFAULT_LOGDIR = ROOT / "runs" / "agentdojo_upstream"
DEFAULT_PROGRESS = ROOT / "runs" / "stress_manifest_progress.json"

SPOTLIGHT_DEFENSES = ("spotlighting_with_delimiting",)
BIO04_DEFENSES = ("bio_04", "bio_idea1_provenance_reflection_meta_full")

SCRIPTED_BASELINE = "baseline_1"
SCRIPTED_BIO04 = "idea1_provenance_mlp_bio_04"

SCRIPTED_DATASETS = (
    "data/attacks/idea1_subtle_pollution.jsonl",
    "data/attacks/idea1_subtle_pollution_heldout.jsonl",
    "data/attacks/reflection_process_samples.jsonl",
    "data/attacks/fragmented_shuffle.jsonl",
    "data/attacks/retry_abuse.jsonl",
    "data/attacks/idea2/c1_drattack.jsonl",
    "data/attacks/idea2/c2_cross_node.jsonl",
    "data/attacks/idea2/c3_tool_injection.jsonl",
    "data/attacks/idea2/c4_schema_smuggle.jsonl",
    "data/attacks/idea2/c5_subtle_deception.jsonl",
    "data/attacks/idea2/c6_escalation.jsonl",
)

# AgentDojo attacks often missing from cache; live-none uses this profile first.
DEFAULT_LIVE_EXTRA_PROFILE = "m1_none_sweep_extra"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _benchmark_meta(bdir: Path) -> dict[str, Any]:
    data = _read_json(bdir / "report.json")
    return data or {}


def _parse_log_path(log_path: Path) -> dict[str, str] | None:
    parts = log_path.parts
    if "user_task_" not in str(log_path):
        return None
    try:
        ut_idx = next(i for i, p in enumerate(parts) if p.startswith("user_task_"))
    except StopIteration:
        return None
    user_task = parts[ut_idx]
    suite = parts[ut_idx - 1] if ut_idx > 0 else ""
    attack_key = "unknown"
    defense = "unknown"
    for i, p in enumerate(parts):
        if p == "logs" and i + 2 < len(parts):
            attack_key = parts[i + 1]
            defense = parts[i + 2]
            break
    inj_name = log_path.stem
    return {
        "suite": suite,
        "user_task": user_task,
        "attack": attack_key,
        "defense": defense,
        "injection_raw": inj_name,
    }


def scan_benchmark_episodes(
    benchmark_dirs: list[Path],
    *,
    model_mode: str | None = "deepseek",
) -> list[dict[str, Any]]:
    """Walk benchmark log trees; return one row per (task, defense, attack, injection)."""
    from eval.paper_curated import logical_injection_task_id

    rows: dict[tuple[str, ...], dict[str, Any]] = {}

    for bdir in benchmark_dirs:
        if not bdir.is_dir():
            continue
        bench_meta = _benchmark_meta(bdir)
        bench_model = bench_meta.get("model_mode")
        if model_mode and bench_model not in (None, model_mode):
            continue

        logs_root = bdir / "logs"
        if not logs_root.exists():
            continue
        mtime = bdir.stat().st_mtime

        for log_path in logs_root.glob("**/injection_task_*.json"):
            parsed = _parse_log_path(log_path)
            if parsed is None:
                continue
            data = _read_json(log_path)
            if data is None:
                continue

            suite = parsed["suite"]
            try:
                logical_inj = logical_injection_task_id(suite, parsed["injection_raw"])
            except ValueError:
                logical_inj = parsed["injection_raw"]

            attack_success = bool(data.get("security", False))
            key = (
                suite,
                parsed["user_task"],
                parsed["attack"],
                logical_inj,
                parsed["defense"],
                bench_model or model_mode or "unknown",
            )
            prev = rows.get(key)
            if prev and prev.get("_mtime", 0) >= mtime:
                continue

            rows[key] = {
                "suite": suite,
                "user_task": parsed["user_task"],
                "attack": parsed["attack"],
                "injection_task": logical_inj,
                "defense": parsed["defense"],
                "model_mode": bench_model or model_mode or "unknown",
                "utility": bool(data.get("utility", False)),
                "attack_success": attack_success,
                "defense_success": not attack_success,
                "log_path": str(log_path),
                "benchmark_dir": str(bdir),
                "_mtime": mtime,
            }

    out = list(rows.values())
    for row in out:
        row.pop("_mtime", None)
    return out


def discover_benchmark_dirs(logdir: Path) -> list[Path]:
    if not logdir.is_dir():
        return []
    return sorted(logdir.glob("benchmark_*"), key=lambda p: p.stat().st_mtime)


def _cell_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        row["suite"],
        row["user_task"],
        row["attack"],
        row["injection_task"],
        row["model_mode"],
    )


def classify_agentdojo(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Group episodes by task cell and classify none-usable / spotlight gaps."""
    by_cell: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for ep in episodes:
        ck = _cell_key(ep)
        prev = by_cell[ck].get(ep["defense"])
        if prev is None or ep.get("log_path", "") > prev.get("log_path", ""):
            by_cell[ck][ep["defense"]] = ep

    none_usable: list[dict[str, Any]] = []
    spotlight_gaps: list[dict[str, Any]] = []
    bio04_wins: list[dict[str, Any]] = []
    stress_valid_batches: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)

    for ck, defenses in by_cell.items():
        suite, user_task, attack, injection, model = ck
        none_ep = defenses.get("none")
        if none_ep is None:
            continue

        cell_base = {
            "suite": suite,
            "user_task": user_task,
            "attack": attack,
            "injection_task": injection,
            "model_mode": model,
            "none_utility": none_ep["utility"],
            "none_attack_success": none_ep["attack_success"],
            "log_path": none_ep.get("log_path"),
            "benchmark_dir": none_ep.get("benchmark_dir"),
        }

        if none_ep["attack_success"]:
            none_usable.append(dict(cell_base))

        for spot_def in SPOTLIGHT_DEFENSES:
            spot_ep = defenses.get(spot_def)
            if spot_ep and none_ep["attack_success"] and spot_ep["attack_success"]:
                spotlight_gaps.append(
                    {
                        **cell_base,
                        "spotlight_defense": spot_def,
                        "spotlight_attack_success": True,
                        "spotlight_utility": spot_ep["utility"],
                        "spotlight_log_path": spot_ep.get("log_path"),
                    }
                )

        for bio_def in BIO04_DEFENSES:
            bio_ep = defenses.get(bio_def)
            if bio_ep and none_ep["attack_success"] and not bio_ep["attack_success"]:
                bio04_wins.append(
                    {
                        **cell_base,
                        "bio_defense": bio_def,
                        "bio_utility": bio_ep["utility"],
                        "bio_log_path": bio_ep.get("log_path"),
                    }
                )

        batch_key = (suite, attack, injection, model)
        stress_valid_batches[batch_key].append(none_ep)

    batch_summaries: list[dict[str, Any]] = []
    for (suite, attack, injection, model), items in sorted(stress_valid_batches.items()):
        n = len(items)
        none_asr = sum(bool(x["attack_success"]) for x in items) / max(n, 1)
        batch_summaries.append(
            {
                "suite": suite,
                "attack": attack,
                "injection_task": injection,
                "model_mode": model,
                "n_tasks": n,
                "none_ASR": round(none_asr, 4),
                "none_ASR_pct": round(100 * none_asr, 2),
                "stress_valid": none_asr > 0 and none_asr < 0.9,
                "stress_invalid_reason": (
                    "none_ASR=0"
                    if none_asr == 0
                    else ("none_ASR>=90%" if none_asr >= 0.9 else None)
                ),
            }
        )

    spotlight_gaps.sort(key=lambda x: (x["suite"], x["attack"], x["user_task"]))
    none_usable.sort(key=lambda x: (x["suite"], x["attack"], x["user_task"]))
    bio04_wins.sort(key=lambda x: (x["suite"], x["attack"], x["user_task"]))
    batch_summaries.sort(key=lambda x: (-x["none_ASR"], x["suite"], x["attack"]))

    return {
        "n_episodes": len(episodes),
        "n_cells": len(by_cell),
        "none_usable": none_usable,
        "n_none_usable": len(none_usable),
        "spotlight_gaps": spotlight_gaps,
        "n_spotlight_gaps": len(spotlight_gaps),
        "bio_04_wins": bio04_wins,
        "n_bio_04_wins": len(bio04_wins),
        "batch_summaries": batch_summaries,
        "stress_valid_batches": [b for b in batch_summaries if b["stress_valid"]],
    }


def load_scripted_samples(*, require_scripted_outputs: bool = True) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in SCRIPTED_DATASETS:
        path = ROOT / rel
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("benign") is True:
                    continue
                is_attack = row.get("label") == "attack" or row.get("benign") is False
                if not is_attack:
                    continue
                if require_scripted_outputs and not row.get("scripted_outputs"):
                    continue
                sid = row.get("id", "")
                if sid in seen:
                    continue
                seen.add(sid)
                row["_dataset"] = rel
                samples.append(row)
    return samples


def run_scripted_sweep(
    *,
    configs: tuple[str, ...] = (SCRIPTED_BASELINE, SCRIPTED_BIO04),
) -> dict[str, Any]:
    from bio_harness.config import CONFIGS_DIR, load_yaml
    from bio_harness.harness.graph import build_runner
    from eval.scripted_runner import run_scripted

    ablations = load_yaml("ablations.yaml") or {}
    cfg_map = ablations.get("configs") or {}

    samples = load_scripted_samples()
    results_by_config: dict[str, list[dict[str, Any]]] = {c: [] for c in configs}

    for cfg_name in configs:
        if cfg_name not in cfg_map:
            raise KeyError(f"Unknown config {cfg_name!r} in {CONFIGS_DIR / 'ablations.yaml'}")
        runner = build_runner(cfg_name)
        for sample in samples:
            result = run_scripted(runner, sample)
            attack_success = bool(result.harmful) and not bool(result.blocked)
            results_by_config[cfg_name].append(
                {
                    "sample_id": sample.get("id"),
                    "attack_type": sample.get("attack_type"),
                    "dataset": sample.get("_dataset") or _sample_dataset(sample.get("id", "")),
                    "config": cfg_name,
                    "blocked": bool(result.blocked),
                    "harmful": bool(result.harmful),
                    "attack_success": attack_success,
                    "escape_layer": result.escape_layer,
                }
            )

    baseline_rows = {r["sample_id"]: r for r in results_by_config[SCRIPTED_BASELINE]}
    bio_rows = {r["sample_id"]: r for r in results_by_config.get(SCRIPTED_BIO04, [])}

    scripted_usable: list[dict[str, Any]] = []
    scripted_bio04_wins: list[dict[str, Any]] = []

    for sid, base in baseline_rows.items():
        if not base["attack_success"]:
            continue
        entry = {
            "sample_id": sid,
            "attack_type": base["attack_type"],
            "dataset": base["dataset"],
            "baseline_blocked": base["blocked"],
            "baseline_harmful": base["harmful"],
            "escape_layer": base["escape_layer"],
        }
        scripted_usable.append(entry)
        bio = bio_rows.get(sid)
        if bio and not bio["attack_success"]:
            scripted_bio04_wins.append(
                {
                    **entry,
                    "bio_blocked": bio["blocked"],
                    "bio_escape_layer": bio["escape_layer"],
                }
            )

    by_attack: dict[str, dict[str, int]] = defaultdict(lambda: {"usable": 0, "bio_wins": 0})
    for row in scripted_usable:
        by_attack[row["attack_type"]]["usable"] += 1
    for row in scripted_bio04_wins:
        by_attack[row["attack_type"]]["bio_wins"] += 1

    return {
        "n_samples": len(samples),
        "configs": list(configs),
        "scripted_usable": scripted_usable,
        "n_scripted_usable": len(scripted_usable),
        "scripted_bio_04_wins": scripted_bio04_wins,
        "n_scripted_bio_04_wins": len(scripted_bio04_wins),
        "by_attack_type": dict(by_attack),
        "baseline_asr": round(
            sum(1 for r in results_by_config[SCRIPTED_BASELINE] if r["attack_success"]) / max(len(samples), 1),
            4,
        ),
        "bio_04_asr": round(
            sum(1 for r in results_by_config.get(SCRIPTED_BIO04, []) if r["attack_success"]) / max(len(samples), 1),
            4,
        )
        if SCRIPTED_BIO04 in results_by_config
        else None,
    }


def _sample_dataset(sample_id: str) -> str:
    if sample_id.startswith("c1_"):
        return "idea2/c1_drattack"
    if sample_id.startswith("c2_"):
        return "idea2/c2_cross_node"
    if sample_id.startswith("c3_"):
        return "idea2/c3_tool_injection"
    if sample_id.startswith("c4_"):
        return "idea2/c4_schema_smuggle"
    if sample_id.startswith("c5_"):
        return "idea2/c5_subtle_deception"
    if sample_id.startswith("c6_"):
        return "idea2/c6_escalation"
    if sample_id.startswith("subtle_") or "paraphrase" in sample_id:
        return "idea1_subtle_pollution"
    if sample_id.startswith("heldout_"):
        return "idea1_subtle_pollution_heldout"
    if sample_id.startswith("refl_"):
        return "reflection_process_samples"
    if "fragment" in sample_id or sample_id.startswith("frag_"):
        return "fragmented_shuffle"
    if sample_id.startswith("retry_"):
        return "retry_abuse"
    return "unknown"


def build_seed_profile(manifest: dict[str, Any]) -> dict[str, Any]:
    """Build a curated profile from spotlight gaps + none-usable cells."""
    tasks: dict[str, list[str]] = defaultdict(list)
    attacks: set[str] = set()
    injections: set[str] = set()

    priority = manifest.get("agentdojo", {}).get("spotlight_gaps") or []
    if not priority:
        priority = manifest.get("agentdojo", {}).get("none_usable") or []

    for row in priority[:40]:
        suite = row["suite"]
        ut = row["user_task"]
        if ut not in tasks[suite]:
            tasks[suite].append(ut)
        attacks.add(row["attack"])
        injections.add(row["injection_task"])

    suite_quotas = {s: len(ts) for s, ts in tasks.items()}
    return {
        "name": "m1_manifest_seed",
        "suite_quotas": suite_quotas,
        "anchor_tasks": dict(tasks),
        "attacks": sorted(attacks) or ["important_instructions_persona"],
        "injection_tasks": sorted(injections) or ["injection_task_0"],
        "defenses": [
            "none",
            "spotlighting_with_delimiting",
            "transformers_pi_detector",
            "bio_04",
        ],
        "model_modes": ["deepseek"],
        "replicates": 1,
        "stress_check": True,
        "description": "Auto-generated from stress_manifest spotlight gaps / none-usable cells",
    }


def run_live_none_sweep(
    *,
    profile_name: str,
    logdir: Path,
    progress_path: Path,
    model_mode: str = "deepseek",
    force_rerun: bool = False,
) -> list[Path]:
    import eval.attacks.stress_attacks  # noqa: F401

    from eval.paper_curated import load_curated_profile, resolve_injection_task_id
    from eval.run_paper_suite import load_progress, save_progress, suite_run_key

    profile = load_curated_profile(profile_name)
    profile = dict(profile)
    profile["defenses"] = ["none"]
    progress = load_progress(progress_path)
    run_dirs: list[Path] = []

    suites = sorted({t["suite"] for t in profile["tasks"]})
    for attack in profile["attacks"]:
        for injection_task in profile["injection_tasks"]:
            for suite in suites:
                key = suite_run_key(model_mode, attack, injection_task, suite)
                tasks = [t["user_task"] for t in profile["tasks"] if t["suite"] == suite]
                if not force_rerun and key in progress.get("completed", {}):
                    bench = Path(progress["completed"][key]["run_dir"])
                    if bench.exists():
                        run_dirs.append(bench)
                    continue

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
                    "--defense",
                    "none",
                    "--logdir",
                    str(logdir),
                ]
                for ut in tasks:
                    cmd.extend(["--user-task", ut])
                print(f"[live-none] {' '.join(cmd[-8:])} …", flush=True)
                proc = subprocess.run(cmd, cwd=ROOT)
                if proc.returncode != 0:
                    raise SystemExit(f"none sweep failed for {key} (rc={proc.returncode})")

                candidates = sorted(logdir.glob("benchmark_*"), key=lambda p: p.stat().st_mtime, reverse=True)
                if candidates:
                    bench_dir = candidates[0]
                    run_dirs.append(bench_dir)
                    progress.setdefault("completed", {})[key] = {
                        "run_dir": str(bench_dir.resolve()),
                        "returncode": proc.returncode,
                    }
                    save_progress(progress_path, progress)
    return run_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stress manifest from AgentDojo + scripted harness")
    parser.add_argument("--scan-only", action="store_true", help="Only scan cached benchmark logs (default)")
    parser.add_argument("--scripted", action="store_true", help="Run scripted harness sweep")
    parser.add_argument("--live-none", action="store_true", help="Run none-only live sweep for profile gaps")
    parser.add_argument("--profile", default="m1_none_sweep", help="Profile for --live-none")
    parser.add_argument(
        "--live-extra",
        action="store_true",
        help=f"Run none-only live sweep with {DEFAULT_LIVE_EXTRA_PROFILE} (injecagent/direct/ignore_previous)",
    )
    parser.add_argument("--logdir", type=Path, default=DEFAULT_LOGDIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--model-mode", default="deepseek")
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument("--write-seed-yaml", type=Path, default=None, help="Write m1_manifest_seed yaml snippet")
    args = parser.parse_args()

    if args.live_extra:
        args.live_none = True
        args.profile = DEFAULT_LIVE_EXTRA_PROFILE

    if not any((args.scan_only, args.scripted, args.live_none)):
        args.scan_only = True

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_mode": args.model_mode,
        "logdir": str(args.logdir),
    }

    benchmark_dirs = discover_benchmark_dirs(args.logdir)
    if args.live_none:
        new_dirs = run_live_none_sweep(
            profile_name=args.profile,
            logdir=args.logdir,
            progress_path=args.progress,
            model_mode=args.model_mode,
            force_rerun=args.force_rerun,
        )
        for d in new_dirs:
            if d not in benchmark_dirs:
                benchmark_dirs.append(d)

    if args.scan_only or args.live_none:
        episodes = scan_benchmark_episodes(benchmark_dirs, model_mode=args.model_mode)
        agentdojo = classify_agentdojo(episodes)
        agentdojo["n_benchmark_dirs"] = len(benchmark_dirs)
        manifest["agentdojo"] = agentdojo
        manifest["seed_profile"] = build_seed_profile(manifest)

    if args.scripted:
        manifest["scripted"] = run_scripted_sweep()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Wrote {args.output}", flush=True)

    if args.scan_only or args.live_none:
        adj = manifest.get("agentdojo", {})
        print(
            f"AgentDojo: {adj.get('n_none_usable', 0)} none-usable, "
            f"{adj.get('n_spotlight_gaps', 0)} spotlight gaps, "
            f"{adj.get('n_bio_04_wins', 0)} bio_04 wins, "
            f"{len(adj.get('stress_valid_batches') or [])} stress-valid batches",
            flush=True,
        )
    if args.scripted:
        sc = manifest.get("scripted", {})
        print(
            f"Scripted: {sc.get('n_scripted_usable', 0)} usable / "
            f"{sc.get('n_samples', 0)} samples, "
            f"{sc.get('n_scripted_bio_04_wins', 0)} bio_04 wins",
            flush=True,
        )

    if args.write_seed_yaml and manifest.get("seed_profile"):
        import yaml

        seed = manifest["seed_profile"]
        args.write_seed_yaml.parent.mkdir(parents=True, exist_ok=True)
        with args.write_seed_yaml.open("w", encoding="utf-8") as f:
            yaml.safe_dump({seed["name"]: seed}, f, sort_keys=False, allow_unicode=True)
        print(f"Wrote seed profile → {args.write_seed_yaml}", flush=True)


if __name__ == "__main__":
    main()
