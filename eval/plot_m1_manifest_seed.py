#!/usr/bin/env python3
"""Visualize m1_manifest_seed (spotlight-gap seed) live results.

Reads paper_m1_manifest_seed_progress.json and produces:
- 01_utility_security_scatter.png
- 02_defense_bars.png
- 03_security_delta_spotlight_vs_bio.png
- 04_paper_comparable_table.png
- 05_suite_attack_heatmap.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRESS = ROOT / "runs" / "paper_m1_manifest_seed_progress.json"
DEFAULT_OUT = ROOT / "figures" / "m1_manifest_seed"

DEFENSE_ORDER = ["none", "spotlighting_with_delimiting", "transformers_pi_detector", "bio_04"]
DEFENSE_LABELS = {
    "none": "none",
    "spotlighting_with_delimiting": "spotlight",
    "transformers_pi_detector": "π-detector",
    "bio_04": "bio_04",
}
DEFENSE_COLORS = {
    "none": "#9ca3af",
    "spotlighting_with_delimiting": "#60a5fa",
    "transformers_pi_detector": "#f59e0b",
    "bio_04": "#10b981",
}


def _setup_style() -> None:
    sns.set_theme(style="whitegrid", context="talk", font_scale=0.85)
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "axes.titleweight": "bold",
        }
    )


def load_progress(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def batch_rows(gate_results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, gate in gate_results.items():
        parts = key.split("|")
        if len(parts) < 4:
            continue
        metrics = gate.get("metrics", {})
        for defense, vals in metrics.get("per_defense", {}).items():
            rows.append(
                {
                    "batch": key,
                    "model_mode": parts[0],
                    "attack": parts[1],
                    "injection_task": parts[2],
                    "suite": parts[3],
                    "stress_ok": bool(gate.get("stress_ok")),
                    "paper_comparable": bool(gate.get("paper_comparable")),
                    "defense": defense,
                    "utility": float(vals.get("utility", 0)) * 100,
                    "security": float(vals.get("security", 0)) * 100,
                    "asr": float(vals.get("ASR", 0)) * 100,
                    "n": int(vals.get("n", 0)),
                }
            )
    return rows


def plot_utility_security_scatter(df: pd.DataFrame, out: Path) -> None:
    """Scatter: each defense = one point, averaged over stress-valid batches."""
    stress = df[df["stress_ok"]].copy()
    if stress.empty:
        return
    avg = (
        stress.groupby("defense")
        .agg(utility=("utility", "mean"), security=("security", "mean"))
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(7, 7))
    for _, row in avg.iterrows():
        d = row["defense"]
        ax.scatter(
            row["utility"],
            row["security"],
            s=300,
            c=DEFENSE_COLORS.get(d, "#333"),
            edgecolors="white",
            linewidths=1.2,
            zorder=3,
        )
        ax.annotate(
            DEFENSE_LABELS.get(d, d),
            (row["utility"], row["security"]),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=11,
            fontweight="bold",
        )
    ax.set_xlabel("Utility (%)")
    ax.set_ylabel("Security (%)")
    ax.set_title("m1_manifest_seed: utility vs security trade-off\n(averaged over stress-valid batches)")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3)
    fig.savefig(out / "01_utility_security_scatter.png")
    plt.close(fig)


def plot_defense_bars(df: pd.DataFrame, out: Path) -> None:
    """Grouped bars: utility + security per defense (stress-valid only)."""
    stress = df[df["stress_ok"]].copy()
    if stress.empty:
        return
    avg = (
        stress.groupby("defense")
        .agg(utility=("utility", "mean"), security=("security", "mean"))
        .reindex(DEFENSE_ORDER)
        .reset_index()
    )
    labels = [DEFENSE_LABELS[d] for d in avg["defense"]]
    x = np.arange(len(avg))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.bar(x - width / 2, avg["utility"], width, label="Utility", color="#60a5fa")
    ax.bar(x + width / 2, avg["security"], width, label="Security", color="#34d399")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Percent")
    ax.set_title("Defense comparison: utility & security on stress-valid seed batches")
    ax.legend()
    for i, (u, s) in enumerate(zip(avg["utility"], avg["security"])):
        ax.text(i - width / 2, u + 2, f"{u:.0f}", ha="center", fontsize=9)
        ax.text(i + width / 2, s + 2, f"{s:.0f}", ha="center", fontsize=9)
    fig.savefig(out / "02_defense_bars.png")
    plt.close(fig)


def plot_security_delta(df: pd.DataFrame, out: Path) -> None:
    """Bar: security gain of bio_04 over spotlight per batch."""
    stress = df[df["stress_ok"]].copy()
    if stress.empty:
        return
    pivot = stress.pivot_table(
        index=["suite", "attack", "injection_task"],
        columns="defense",
        values="security",
        aggfunc="mean",
    ).reset_index()
    pivot = pivot.dropna(subset=["bio_04", "spotlighting_with_delimiting"])
    pivot["delta"] = pivot["bio_04"] - pivot["spotlighting_with_delimiting"]
    pivot = pivot.sort_values("delta", ascending=True)
    y_labels = [f"{r['suite']}\n{r['attack'][:20]}\n{r['injection_task']}" for _, r in pivot.iterrows()]
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = ["#ef4444" if d < 0 else "#10b981" for d in pivot["delta"]]
    ax.barh(range(len(pivot)), pivot["delta"], color=colors)
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(y_labels, fontsize=8)
    ax.set_xlabel("Security gain of bio_04 vs spotlight (percentage points)")
    ax.set_title("bio_04 security improvement over spotlighting\n(stress-valid batches)")
    ax.axvline(0, color="black", linewidth=0.8)
    for i, d in enumerate(pivot["delta"]):
        ax.text(d + 1, i, f"+{d:.0f}" if d > 0 else f"{d:.0f}", va="center", fontsize=9)
    fig.savefig(out / "03_security_delta_spotlight_vs_bio.png")
    plt.close(fig)


def plot_paper_comparable_table(df: pd.DataFrame, out: Path) -> None:
    """Table of paper-comparable batches."""
    paper = df[df["paper_comparable"]].copy()
    if paper.empty:
        return
    avg = (
        paper.groupby("defense")
        .agg(utility=("utility", "mean"), security=("security", "mean"))
        .reindex(DEFENSE_ORDER)
        .reset_index()
    )
    avg["defense_label"] = avg["defense"].map(DEFENSE_LABELS)
    table_data = avg[["defense_label", "utility", "security"]].values
    table_data = [[c] + [f"{x:.1f}" for x in row[1:]] for c, row in zip(avg["defense_label"], table_data)]
    fig, ax = plt.subplots(figsize=(8, 2.5 + 0.4 * len(avg)))
    ax.axis("off")
    table = ax.table(
        cellText=table_data,
        colLabels=["Defense", "Utility (%)", "Security (%)"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    ax.set_title("Paper-comparable seed batches (stress-valid + defense passes)", pad=20)
    fig.savefig(out / "04_paper_comparable_table.png")
    plt.close(fig)


def plot_suite_attack_heatmap(df: pd.DataFrame, out: Path) -> None:
    """Heatmaps for security and utility by (suite, attack) for bio_04 and spotlight."""
    stress = df[df["stress_ok"] & df["defense"].isin(["bio_04", "spotlighting_with_delimiting"])].copy()
    if stress.empty:
        return
    pivot_sec = stress.pivot_table(
        index=["suite", "attack"], columns="defense", values="security", aggfunc="mean"
    )
    pivot_util = stress.pivot_table(
        index=["suite", "attack"], columns="defense", values="utility", aggfunc="mean"
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, pivot, title in zip(
        axes,
        [pivot_sec, pivot_util],
        ["Security (%)", "Utility (%)"],
    ):
        sns.heatmap(
            pivot,
            annot=True,
            fmt=".0f",
            cmap="RdYlGn",
            vmin=0,
            vmax=100,
            cbar_kws={"label": title},
            ax=ax,
        )
        ax.set_title(f"{title} by suite × attack")
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(out / "05_suite_attack_heatmap.png")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    _setup_style()
    args.out.mkdir(parents=True, exist_ok=True)

    progress = load_progress(args.progress)
    rows = batch_rows(progress.get("gate_results", {}))
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No gate results found in progress file.")

    plot_utility_security_scatter(df, args.out)
    plot_defense_bars(df, args.out)
    plot_security_delta(df, args.out)
    plot_paper_comparable_table(df, args.out)
    plot_suite_attack_heatmap(df, args.out)

    # Also save aggregated CSV
    summary = df[df["stress_ok"]].groupby("defense").agg(
        utility=("utility", "mean"),
        security=("security", "mean"),
        asr=("asr", "mean"),
        n_batches=("batch", "nunique"),
    ).reindex(DEFENSE_ORDER)
    summary.to_csv(args.out / "summary_stress_valid.csv")

    print(f"Figures written to {args.out}")


if __name__ == "__main__":
    main()
