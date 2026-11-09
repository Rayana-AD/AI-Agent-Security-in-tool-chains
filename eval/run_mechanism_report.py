#!/usr/bin/env python3
"""Mechanism (E4) report from completed live benchmark logs — partial runs OK."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.paper_curated import load_curated_profile
from eval.paper_mechanism import scan_benchmark_dirs, summarize_mechanisms

MECH_LABELS = {
    "output_withhold": "output withhold",
    "metadata_strip": "metadata strip",
    "unified_risk": "unified risk",
    "reflection": "reflection",
    "gate_drift": "gate / drift",
    "feature_shuffle": "feature shuffle",
    "channel_escalation": "channel escalation",
    "harmful_pattern": "harmful pattern",
    "other_block": "other block",
    "attack_success": "attack success",
    "task_incomplete": "task incomplete",
    "success": "clean success",
    "unknown": "unknown",
}

BIO_DEFENSES = [
    "bio_idea1",
    "bio_idea1_provenance_reflection",
    "bio_idea1_provenance_reflection_meta_full",
]


def _load_progress(path: Path) -> dict:
    if not path.exists():
        return {"completed": {}, "active": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _select_dirs(progress: dict, *, model_mode: str | None) -> tuple[list[Path], dict[str, str]]:
    dirs: list[Path] = []
    key_to_dir: dict[str, str] = {}
    for key, meta in (progress.get("completed") or {}).items():
        if model_mode and not key.startswith(f"{model_mode}|"):
            continue
        run_dir = Path(meta["run_dir"])
        if run_dir.is_dir():
            dirs.append(run_dir)
            key_to_dir[key] = str(run_dir.resolve())
    for key, meta in (progress.get("active") or {}).items():
        if model_mode and not key.startswith(f"{model_mode}|"):
            continue
        run_dir = Path(meta.get("run_dir", ""))
        if run_dir.is_dir():
            dirs.append(run_dir)
            key_to_dir[key] = str(run_dir.resolve())
    return list(dict.fromkeys(dirs)), key_to_dir


def fig_mechanism_taxonomy(by_mechanism: dict, out: Path, title: str) -> None:
    if not by_mechanism:
        return
    items = sorted(by_mechanism.items(), key=lambda kv: kv[1], reverse=True)
    labels = [MECH_LABELS.get(k, k) for k, _ in items]
    vals = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(9, 4))
    sns.barplot(x=vals, y=labels, ax=ax, color="#2F6F73")
    ax.set_xlabel("Episodes")
    ax.set_title(title)
    fig.savefig(out / "fig_e4_mechanism_taxonomy.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_mechanism_by_defense(episodes: list[dict], out: Path) -> None:
    bio_eps = [e for e in episodes if e.get("defense") in BIO_DEFENSES]
    if not bio_eps:
        bio_eps = [e for e in episodes if str(e.get("defense", "")).startswith("bio_")]
    if not bio_eps:
        return
    df = pd.DataFrame(bio_eps)
    cross = pd.crosstab(df["defense"], df["dominant_mechanism"])
    cross = cross.reindex([d for d in BIO_DEFENSES if d in cross.index] + [x for x in cross.index if x not in BIO_DEFENSES])
    fig, ax = plt.subplots(figsize=(10, 4.5))
    cross.plot(kind="bar", stacked=True, ax=ax, colormap="crest")
    ax.set_ylabel("Episodes")
    ax.set_xlabel("")
    ax.set_title("E4 Design mechanism by BioHarness variant (live logs)")
    ax.legend(title="Mechanism", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    plt.xticks(rotation=15, ha="right")
    fig.savefig(out / "fig_e4_mechanism_by_bio_variant.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_mechanism_by_suite(episodes: list[dict], out: Path) -> None:
    bio_eps = [e for e in episodes if str(e.get("defense", "")).startswith("bio_")]
    if not bio_eps:
        return
    df = pd.DataFrame(bio_eps)
    cross = pd.crosstab(df["suite"], df["dominant_mechanism"])
    fig, ax = plt.subplots(figsize=(8, 4))
    cross.plot(kind="bar", stacked=True, ax=ax, colormap="mako")
    ax.set_ylabel("Episodes")
    ax.set_title("E4 Bio mechanism by suite")
    ax.legend(title="Mechanism", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    plt.xticks(rotation=0)
    fig.savefig(out / "fig_e4_mechanism_by_suite.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_mechanism_by_task(episodes: list[dict], out: Path) -> None:
    bio_eps = [e for e in episodes if str(e.get("defense", "")).startswith("bio_")]
    if not bio_eps:
        return
    df = pd.DataFrame(bio_eps)
    if "task_type" not in df.columns:
        return
    top_tasks = df["task_type"].value_counts().head(12).index
    sub = df[df["task_type"].isin(top_tasks)]
    cross = pd.crosstab(sub["task_type"], sub["dominant_mechanism"])
    fig, ax = plt.subplots(figsize=(10, 5))
    cross.plot(kind="barh", stacked=True, ax=ax, colormap="viridis")
    ax.set_xlabel("Episodes")
    ax.set_title("E4 Bio mechanism by task type")
    ax.legend(title="Mechanism", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.savefig(out / "fig_e4_mechanism_by_task.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_mechanism_table(summary: dict, out: Path) -> None:
    lines = [
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Mechanism & Episodes & Share (\%) \\",
        r"\midrule",
    ]
    total = max(1, summary.get("n_episodes", 0))
    for mech, count in sorted((summary.get("by_mechanism") or {}).items(), key=lambda kv: -kv[1]):
        label = MECH_LABELS.get(mech, mech).replace("_", r"\_")
        lines.append(f"{label} & {count} & {100 * count / total:.1f} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (out / "table_e4_mechanism_summary.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=ROOT / "runs" / "paper_m1_live_progress.json",
    )
    parser.add_argument("--model-mode", default="deepseek", help="Filter progress keys (e.g. deepseek)")
    parser.add_argument("--profile", default="m1", choices=["m1", "workshop"])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--include-active", action="store_true", help="Include in-progress benchmark dir")
    args = parser.parse_args()

    progress = _load_progress(args.progress_file)
    if not args.include_active:
        progress = {"completed": progress.get("completed") or {}, "active": {}}

    bench_dirs, key_to_dir = _select_dirs(progress, model_mode=args.model_mode or None)
    if not bench_dirs:
        raise SystemExit(f"No benchmark dirs found in {args.progress_file} for model={args.model_mode}")

    profile = load_curated_profile(args.profile)
    episodes = scan_benchmark_dirs(
        bench_dirs,
        curated_tasks=profile["tasks"],
        model_mode=args.model_mode,
        progress_keys=key_to_dir,
    )
    summary = summarize_mechanisms(episodes)
    summary["model_mode"] = args.model_mode
    summary["benchmark_dirs"] = [str(p) for p in bench_dirs]
    summary["progress_keys"] = list(key_to_dir.keys())

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or (ROOT / "runs" / f"mechanism_report_{args.model_mode}_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": ts,
        "model_mode": args.model_mode,
        "n_benchmark_dirs": len(bench_dirs),
        "summary": summary,
        "episodes": episodes,
    }
    (out_dir / "mechanism_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )

    sns.set_theme(style="whitegrid", context="paper")
    title = f"E4 Dominant mechanism — {args.model_mode} ({summary['n_episodes']} episodes, partial OK)"
    fig_mechanism_taxonomy(summary["by_mechanism"], out_dir, title)
    fig_mechanism_by_defense(episodes, out_dir)
    fig_mechanism_by_suite(episodes, out_dir)
    fig_mechanism_by_task(episodes, out_dir)
    write_mechanism_table(summary, out_dir)

    print(json.dumps({k: v for k, v in summary.items() if k != "by_defense"}, indent=2))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
