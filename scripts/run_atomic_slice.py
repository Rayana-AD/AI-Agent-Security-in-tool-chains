#!/usr/bin/env python3
"""Run within-episode atomic_split attacks on DeepSeek (m1_atomic_slice).

Defenses: none, bio_04, task_shield, melon.
Progress: runs/paper_atomic_slice_deepseek_progress.json
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
import eval.attacks.atomic_split  # noqa: F401

from scripts.run_m1_gated_rerun import batch_metrics, iter_batches, run_one_batch
from eval.paper_curated import load_curated_profile
from eval.run_paper_suite import load_progress, save_progress

DEFAULT_PROGRESS = ROOT / "runs" / "paper_atomic_slice_deepseek_progress.json"
DEFAULT_DEFENSES = ["none", "bio_04", "task_shield", "melon"]


def summarize(progress_path: Path, profile: dict) -> dict:
    progress = load_progress(progress_path)
    completed = progress.get("completed") or {}
    rows = []
    for key, meta in completed.items():
        parts = key.split("|")
        if len(parts) < 4 or parts[0] != "deepseek":
            continue
        model, attack, inj, suite = parts[0], parts[1], parts[2], parts[3]
        m = batch_metrics(
            Path(meta["run_dir"]),
            profile=profile,
            model_mode=model,
            attack=attack,
            injection_task=inj,
            suite=suite,
        )
        rows.append({"key": key, "attack": attack, "suite": suite, **m})

    by_def: dict[str, list] = {}
    by_attack: dict[str, dict[str, list]] = {}
    for r in rows:
        for d, vals in (r.get("per_defense") or {}).items():
            by_def.setdefault(d, []).append(vals)
            by_attack.setdefault(r["attack"], {}).setdefault(d, []).append(vals)

    def _macro(items: list) -> dict:
        us = [x["utility"] for x in items if x.get("utility") is not None]
        ss = [x["security"] for x in items if x.get("security") is not None]
        return {
            "n": len(items),
            "utility": round(sum(us) / len(us), 4) if us else None,
            "security": round(sum(ss) / len(ss), 4) if ss else None,
        }

    out = {
        "n_batches": len(rows),
        "macro_by_defense": {d: _macro(v) for d, v in by_def.items()},
        "macro_by_attack": {
            a: {d: _macro(v) for d, v in dd.items()} for a, dd in by_attack.items()
        },
        "scope_note": (
            "Within-episode atomic IPI (fragment composition). "
            "Not FragFuse-style cross-session memory fusion."
        ),
    }
    out_path = progress_path.with_name(progress_path.stem + "_summary.json")
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2), flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="m1_atomic_slice")
    parser.add_argument("--progress-file", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--start-batch", type=int, default=1)
    parser.add_argument("--max-batches", type=int, default=99)
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--defense", action="append", dest="defenses")
    args = parser.parse_args()

    profile = load_curated_profile(args.profile)
    defenses = list(args.defenses or profile.get("defenses") or DEFAULT_DEFENSES)

    if args.summarize_only:
        summarize(args.progress_file, profile)
        return 0

    batches = iter_batches(["deepseek"], profile)
    start = max(1, args.start_batch) - 1
    selected = batches[start : start + args.max_batches]
    print(
        f"Atomic slice: {len(selected)}/{len(batches)} batches defenses={defenses}",
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
            print(f"WARN batch failed (continue): {e}", flush=True)
            continue
        except Exception as e:
            print(f"WARN batch exception (continue): {e}", flush=True)
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
        progress.setdefault("atomic_metrics", {})[f"{model}|{attack}|{inj}|{suite}"] = (
            metrics.get("per_defense", {})
        )
        save_progress(args.progress_file, progress)
        print(json.dumps(metrics.get("per_defense", {}), indent=2), flush=True)

    summarize(args.progress_file, profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
