#!/usr/bin/env python3
"""Run Task Shield + MELON on the paper 24-condition DeepSeek manifest.

Does NOT re-run none / spotlighting / transformers_pi_detector / bio_04.
Progress: runs/paper_peer_baselines_deepseek_progress.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import eval.attacks.stress_attacks  # noqa: F401

from scripts.run_m1_gated_rerun import batch_metrics, iter_batches, run_one_batch
from eval.paper_curated import load_curated_profile
from eval.run_paper_suite import load_progress, save_progress

DEFAULT_PROGRESS = ROOT / "runs" / "paper_peer_baselines_deepseek_progress.json"
PEER_DEFENSES = ["melon", "task_shield"]


def summarize(progress_path: Path, profile: dict) -> dict:
    progress = load_progress(progress_path)
    completed = progress.get("completed") or {}
    rows = []
    for key, meta in completed.items():
        if ":stress_probe" in key:
            continue
        parts = key.split("|")
        if len(parts) < 4:
            continue
        model, attack, inj, suite = parts[0], parts[1], parts[2], parts[3]
        if model != "deepseek":
            continue
        bench = Path(meta["run_dir"])
        m = batch_metrics(
            bench,
            profile=profile,
            model_mode=model,
            attack=attack,
            injection_task=inj,
            suite=suite,
        )
        rows.append({"key": key, **m})

    by_def: dict[str, list[dict]] = {}
    for r in rows:
        for d, vals in (r.get("per_defense") or {}).items():
            by_def.setdefault(d, []).append(vals)

    macro = {}
    for d, items in by_def.items():
        us = [x["utility"] for x in items if x.get("utility") is not None]
        ss = [x["security"] for x in items if x.get("security") is not None]
        macro[d] = {
            "n_conditions": len(items),
            "utility": round(sum(us) / len(us), 4) if us else None,
            "security": round(sum(ss) / len(ss), 4) if ss else None,
        }
    out = {"n_batches": len(rows), "macro_by_defense": macro}
    out_path = progress_path.with_name(progress_path.stem + "_summary.json")
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2), flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="m1_manifest_seed")
    parser.add_argument("--progress-file", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--start-batch", type=int, default=1)
    parser.add_argument("--max-batches", type=int, default=24)
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument(
        "--defense",
        action="append",
        dest="defenses",
        help="Override peer defenses (default: melon + task_shield)",
    )
    args = parser.parse_args()

    profile = load_curated_profile(args.profile)
    defenses = list(args.defenses or PEER_DEFENSES)

    if args.summarize_only:
        summarize(args.progress_file, profile)
        return 0

    batches = iter_batches(["deepseek"], profile)
    start = max(1, args.start_batch) - 1
    selected = batches[start : start + args.max_batches]
    print(
        f"Peer baselines: {len(selected)} batch(es) defenses={defenses} "
        f"progress={args.progress_file}",
        flush=True,
    )

    for i, (model, attack, inj, suite) in enumerate(selected, start=start + 1):
        print(f"\n>>> batch {i}/{len(batches)} {model}|{attack}|{inj}|{suite}", flush=True)
        try:
            bench = run_one_batch(
                model_mode=model,
                attack=attack,
                injection_task=inj,
                suite=suite,
                profile=profile,
                progress_path=args.progress_file,
                force_rerun=args.force_rerun,
                defenses=defenses,
            )
        except SystemExit as e:
            print(f"WARN batch failed (will continue): {e}", flush=True)
            continue
        except Exception as e:
            print(f"WARN batch exception (will continue): {e}", flush=True)
            continue
        metrics = batch_metrics(
            bench,
            profile=profile,
            model_mode=model,
            attack=attack,
            injection_task=inj,
            suite=suite,
        )
        progress = load_progress(args.progress_file)
        progress.setdefault("peer_metrics", {})[f"{model}|{attack}|{inj}|{suite}"] = metrics.get(
            "per_defense", {}
        )
        save_progress(args.progress_file, progress)
        print(json.dumps(metrics.get("per_defense", {}), indent=2), flush=True)

    summarize(args.progress_file, profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
