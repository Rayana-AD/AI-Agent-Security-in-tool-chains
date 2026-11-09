#!/usr/bin/env python3
"""Paper figures: P0-P1 Pareto/module/mechanism + M2 rigor metrics."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]

SCHEME_LABELS = {
    "I0_withhold": "I0 withhold",
    "I1_metadata_strip": "I1 metadata strip",
    "S2_watch_carveout": "S2 watch carve-out",
    "S3_ipi_light": "S3 IPI-light",
    "S4_unified_risk": "S4 unified risk",
    "S5_full": "S5 full",
    "S0_withhold": "S0 withhold",
    "S1_metadata_strip": "S1 metadata strip",
}

MODULE_LABELS = {
    "M1_minus_watch": "−watch carve-out",
    "M2_minus_ipi_light": "−IPI-light",
    "M3_minus_unified": "−unified risk",
    "M4_minus_per_tool": "−per-tool filter",
    "M6_minus_fidelity": "−fidelity hint",
    "M7_minus_metadata": "−metadata strip",
}

DEFENSE_LABELS = {
    "none": "none",
    "tool_filter": "tool_filter",
    "spotlighting_with_delimiting": "spotlighting",
    "repeat_user_prompt": "repeat_prompt",
    "transformers_pi_detector": "pi_detector",
    "bio_idea1": "bio_idea1",
    "bio_idea1_provenance_reflection": "bio_prov_refl",
    "bio_idea1_provenance_reflection_meta_full": "meta_full",
}

TABLE_DEFENSE_ORDER = [
    "none",
    "tool_filter",
    "spotlighting_with_delimiting",
    "repeat_user_prompt",
    "transformers_pi_detector",
    "bio_idea1",
    "bio_idea1_provenance_reflection",
    "bio_idea1_provenance_reflection_meta_full",
]


def _pct(x: float) -> str:
    return f"{100 * float(x):.1f}"


def _write_tex(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _escape_tex(s: Any) -> str:
    text = str(s).replace("−", "-")
    replacements = {
        "\\": r"\textbackslash{}",
        "_": r"\_",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
        }
    )


def _load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fig_scheme_pareto(rows: list[dict], out: Path) -> None:
    """E1: scheme progression Pareto (offline upper bounds)."""
    df = pd.DataFrame(rows)
    df["label"] = df["scheme_id"].map(lambda x: SCHEME_LABELS.get(x, x))
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(df))
    utility = df["utility_score"] * 100
    security = df["security_score"] * 100
    colors = sns.color_palette("crest", n_colors=len(df))
    ax.plot(x, utility, color="#2F6F73", linewidth=2.2, zorder=2)
    ax.scatter(x, utility, s=95, color=colors, edgecolors="white", linewidths=1.2, zorder=3)
    ax.plot(x, security, color="#C44E52", linewidth=1.5, linestyle=":", label="security lower bound")
    for i, val in enumerate(utility):
        ax.annotate(f"{val:.0f}", (x[i], val), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["label"], rotation=18, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 108)
    ax.set_title("E1 Boundary placement improves utility while preserving security")
    ax.text(
        0.99,
        0.08,
        "security stays at 100% in this offline probe",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#555555",
    )
    fig.savefig(out / "fig_e1_scheme_pareto.png")
    plt.close(fig)


def fig_module_heatmap(deltas: list[dict], out: Path, failure_impact: list[dict] | None = None) -> None:
    """E2: drop-one module delta vs M0_full."""
    if not deltas:
        return
    fi = {x["scheme_id"]: x.get("primary_failure", "") for x in (failure_impact or [])}
    df = pd.DataFrame(deltas)
    df["label"] = df["scheme_id"].map(
        lambda x: f"{MODULE_LABELS.get(x, x)} ({fi.get(x, '')})" if fi.get(x) else MODULE_LABELS.get(x, x)
    )
    df = df.sort_values("utility_delta")
    nonzero = df[(df["utility_delta"].abs() > 1e-9) | (df["security_delta"].abs() > 1e-9)]
    plot_df = nonzero if not nonzero.empty else df
    fig, ax = plt.subplots(figsize=(7.2, max(2.6, 0.55 * len(plot_df) + 1.3)))
    y = np.arange(len(df))
    y = np.arange(len(plot_df))
    ax.barh(y, plot_df["utility_delta"] * 100, height=0.45, label="Δ utility", color="#4C72B0")
    ax.barh(y + 0.45, plot_df["security_delta"] * 100, height=0.45, label="Δ security", color="#C44E52")
    ax.set_yticks(y + 0.225)
    ax.set_yticklabels(plot_df["label"])
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Δ vs M0_full (percentage points)")
    ax.set_title("E2 Modules with measurable effect in the offline probe")
    ax.legend(loc="lower right")
    fig.savefig(out / "fig_e2_module_delta.png")
    plt.close(fig)


def fig_idea1_decomposition(rows: list[dict], out: Path) -> None:
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    x = np.arange(len(df))
    w = 0.35
    ax.bar(x - w / 2, df["utility_score"] * 100, w, label="Utility bound", color="#4C72B0")
    ax.bar(x + w / 2, df["security_score"] * 100, w, label="Security bound", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scheme_id"], rotation=15, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 105)
    ax.set_title("E7 Provenance layer restores security; meta controls restore utility")
    ax.legend()
    fig.savefig(out / "fig_e7_idea1_decomposition.png")
    plt.close(fig)


def fig_mechanism_bars(by_mechanism: dict, out: Path) -> None:
    """E4: dominant mechanism taxonomy from live logs."""
    if not by_mechanism:
        return
    items = sorted(by_mechanism.items(), key=lambda kv: kv[1], reverse=True)
    labels, counts = zip(*items)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = sns.color_palette("muted", n_colors=len(labels))
    ax.barh(list(reversed(labels)), list(reversed(counts)), color=list(reversed(colors)))
    ax.set_xlabel("Episode count")
    ax.set_title("E4 Dominant defense mechanism (curated live logs)")
    fig.savefig(out / "fig_e4_mechanism_taxonomy.png")
    plt.close(fig)


def fig_live_defense_comparison(paired_metrics: dict, out: Path) -> None:
    """P0/P1: utility & security by defense with bootstrap CI."""
    defenses = paired_metrics.get("defenses") or {}
    if not defenses:
        return
    rows = []
    for defense, stats in defenses.items():
        rows.append(
            {
                "defense": DEFENSE_LABELS.get(defense, defense),
                "utility": stats["utility_mean"] * 100,
                "security": stats["security_mean"] * 100,
                "u_lo": stats["utility_ci"]["ci_low"] * 100,
                "u_hi": stats["utility_ci"]["ci_high"] * 100,
                "s_lo": stats["security_ci"]["ci_low"] * 100,
                "s_hi": stats["security_ci"]["ci_high"] * 100,
                "utility_retention": stats["utility_retention"] * 100,
            }
        )
    df = pd.DataFrame(rows).sort_values("utility", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 4.2))

    x = np.arange(len(df))
    ax.bar(x, df["utility"], color="#4C72B0", alpha=0.88)
    ax.errorbar(x, df["utility"], yerr=[df["utility"] - df["u_lo"], df["u_hi"] - df["utility"]], fmt="none", color="black", capsize=4)
    for i, val in enumerate(df["utility"]):
        ax.text(i, min(103, val + 4), f"{val:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["defense"], rotation=18, ha="right")
    ax.set_ylabel("Utility (%)")
    ax.set_title("M2 Live utility with bootstrap 95% CI (security = 100% for all defenses)")
    ax.set_ylim(0, 112)
    fig.tight_layout()
    fig.savefig(out / "fig_m2_live_ci_bars.png")
    plt.close(fig)

    # Retention bar
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(df["defense"], df["utility_retention"], color="#55A868")
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.8)
    ax.set_ylabel("Utility retention vs none (%)")
    ax.set_title("M2 Utility retention")
    ax.set_ylim(0, 110)
    plt.xticks(rotation=25, ha="right")
    fig.savefig(out / "fig_m2_utility_retention.png")
    plt.close(fig)


def fig_hypervolume(hv: dict, out: Path, title: str, fname: str) -> None:
    if not hv:
        return
    labels = list(hv.keys())
    vals = [hv[k] for k in labels]
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.bar(labels, vals, color=sns.color_palette("deep")[0])
    ax.set_ylabel("2D hypervolume")
    ax.set_title(title)
    plt.xticks(rotation=20, ha="right")
    fig.savefig(out / fname)
    plt.close(fig)


def fig_tool_filter_frontier(frontier: dict, out: Path) -> None:
    if not frontier:
        return
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    pts = [
        (frontier.get("anchor_utility", 0) * 100, frontier.get("anchor_security", 0) * 100, frontier.get("anchor", "anchor")),
        (frontier.get("candidate_utility", 0) * 100, frontier.get("candidate_security", 0) * 100, frontier.get("candidate", "candidate")),
    ]
    colors = ["#4C72B0", "#C44E52"]
    for (u, s, name), c in zip(pts, colors):
        ax.scatter(u, s, s=180, c=c, edgecolors="white", linewidths=1.5, zorder=3)
        ax.annotate(DEFENSE_LABELS.get(name, name), (u, s), textcoords="offset points", xytext=(8, 6))
    ax.set_xlabel("Utility (%)")
    ax.set_ylabel("Security (%)")
    ax.set_title("M2 Frontier: meta_full dominates tool_filter on this slice")
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    delta_u = frontier.get("utility_delta_at_similar_security", 0) * 100
    ax.text(0.05, 0.05, f"Δutility = {delta_u:+.1f} pp", transform=ax.transAxes, fontsize=10)
    fig.savefig(out / "fig_m2_tool_filter_frontier.png")
    plt.close(fig)


def fig_per_task_heatmap(live_rows: list[dict], out: Path) -> None:
    if not live_rows:
        return
    df = pd.DataFrame(live_rows)
    df["defense_label"] = df["defense"].map(lambda d: DEFENSE_LABELS.get(d, d))
    df["task_key"] = df["suite"] + "/" + df["user_task"]
    pivot_u = df.pivot_table(index="task_key", columns="defense_label", values="utility", aggfunc="max")
    pivot_s = df.pivot_table(index="task_key", columns="defense_label", values="security", aggfunc="max")
    fig, axes = plt.subplots(1, 2, figsize=(12.5, max(3.8, 0.38 * len(pivot_u) + 1.8)))
    sns.heatmap(pivot_u.astype(float), annot=True, fmt=".0f", cmap="Greens", vmin=0, vmax=1, ax=axes[0], cbar=False, linewidths=0.5, linecolor="white")
    axes[0].set_title("Utility pass by task")
    sns.heatmap(pivot_s.astype(float), annot=True, fmt=".0f", cmap="Blues", vmin=0, vmax=1, ax=axes[1], cbar=False, linewidths=0.5, linecolor="white")
    axes[1].set_title("Security pass by task")
    fig.suptitle("Curated task × defense heatmap", y=1.02)
    fig.tight_layout()
    fig.savefig(out / "fig_p0_task_defense_heatmap.png")
    plt.close(fig)


def fig_multi_task_offline(rows: list[dict], out: Path) -> None:
    """E6: offline bounds across task fixtures (meta_full)."""
    if not rows:
        return
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(df))
    w = 0.35
    ax.bar(x - w / 2, df["utility_score"] * 100, w, label="Utility bound", color="#55A868")
    ax.bar(x + w / 2, df["security_score"] * 100, w, label="Security bound", color="#8172B3")
    ax.set_xticks(x)
    labels = [f"{r['task_id']}\n({r['task_type']})" for r in rows]
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 105)
    ax.set_title("E6 Multi-task offline bounds (meta_full)")
    ax.legend()
    fig.savefig(out / "fig_e6_multi_task_offline.png")
    plt.close(fig)


def fig_mechanism_by_task_type(episodes: list[dict], out: Path) -> None:
    """E4 stacked: mechanism by task type from live logs."""
    if not episodes:
        return
    df = pd.DataFrame(episodes)
    if "user_task_id" not in df.columns:
        return
    cross = pd.crosstab(df["user_task_id"], df["dominant_mechanism"])
    fig, ax = plt.subplots(figsize=(10, 5))
    cross.plot(kind="bar", stacked=True, ax=ax, colormap="tab20")
    ax.set_xlabel("User task")
    ax.set_ylabel("Episodes")
    ax.set_title("E4 Mechanism by task (curated live)")
    ax.legend(bbox_to_anchor=(1.02, 1), fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "fig_e4_mechanism_by_task.png")
    plt.close(fig)


def fig_p1_baseline_comparison(paired_metrics: dict, out: Path) -> None:
    """E5: all defenses utility/security on curated slice."""
    defenses = paired_metrics.get("defenses") or {}
    if len(defenses) < 4:
        return
    rows = []
    for defense, stats in defenses.items():
        rows.append(
            {
                "defense": DEFENSE_LABELS.get(defense, defense),
                "utility": stats["utility_mean"] * 100,
                "security": stats["security_mean"] * 100,
            }
        )
    df = pd.DataFrame(rows).sort_values("utility", ascending=True)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    y = np.arange(len(df))
    ax.barh(y, df["utility"], height=0.4, label="Utility", color="#4C72B0")
    ax.barh(y + 0.4, df["security"], height=0.4, label="Security", color="#C44E52")
    ax.set_yticks(y + 0.2)
    ax.set_yticklabels(df["defense"])
    ax.set_xlim(0, 105)
    ax.set_xlabel("Rate (%)")
    ax.set_title("E5 Paper baselines on curated slice")
    ax.legend(loc="lower right")
    fig.savefig(out / "fig_e5_baseline_comparison.png")
    plt.close(fig)


def table_scheme_progression(rows: list[dict], out: Path) -> None:
    if not rows:
        return
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Scheme & Utility & Security & Visible & Attack blocked \\",
        r"\midrule",
    ]
    for row in rows:
        label = SCHEME_LABELS.get(row["scheme_id"], row["scheme_id"])
        visible = "yes" if row.get("payload_visible") or row.get("id7_visible") else "no"
        attack_blocked = "yes" if row.get("security_score", 0) >= 1 else "no"
        lines.append(
            f"{_escape_tex(label)} & {_pct(row['utility_score'])} & {_pct(row['security_score'])} "
            f"& {_escape_tex(visible)} & {_escape_tex(attack_blocked)} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_e1_scheme_progression.tex", "\n".join(lines))


def table_module_ablation(rows: list[dict], out: Path) -> None:
    if not rows:
        return
    lines = [
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Drop-one variant & Failure class & Utility & $\Delta U$ & Security \\",
        r"\midrule",
    ]
    for row in rows:
        label = MODULE_LABELS.get(row["scheme_id"], row["scheme_id"])
        lines.append(
            f"{_escape_tex(label)} & {_escape_tex(row.get('primary_failure', ''))} "
            f"& {_pct(row['utility_score'])} & {row['utility_delta'] * 100:+.1f} "
            f"& {_pct(row['security_score'])} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_e2_module_ablation.tex", "\n".join(lines))


def _fmt_p(p: float | None) -> str:
    if p is None:
        return "--"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def table_significance(paired_metrics: dict, out: Path) -> None:
    sig = paired_metrics.get("significance") or {}
    comparisons = sig.get("comparisons") or {}
    if not comparisons:
        return
    baseline = sig.get("baseline_defense", "none")
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        rf"Defense vs {_escape_tex(DEFENSE_LABELS.get(baseline, baseline))} & "
        r"$n$ & Util $p$ & Sec $p$ & Discordant (util) \\",
        r"\midrule",
    ]
    ordered = [d for d in TABLE_DEFENSE_ORDER if d in comparisons] + [
        d for d in comparisons if d not in TABLE_DEFENSE_ORDER
    ]
    for defense in ordered:
        if defense == baseline:
            continue
        comp = comparisons[defense]
        util_m = comp.get("utility_mcnemar") or {}
        sec_m = comp.get("security_mcnemar") or {}
        disc = f"{util_m.get('b', 0)}/{util_m.get('c', 0)}"
        lines.append(
            f"{_escape_tex(DEFENSE_LABELS.get(defense, defense))} & {comp.get('n_paired', 0)} "
            f"& {_fmt_p(util_m.get('p_value'))} & {_fmt_p(sec_m.get('p_value'))} "
            f"& {_escape_tex(disc)} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_m2_significance.tex", "\n".join(lines))


def table_cross_model(cross_model: dict, out: Path) -> None:
    models = cross_model.get("models") or []
    if not models:
        return
    candidate = cross_model.get("candidate", "bio_idea1_provenance_reflection_meta_full")
    cand_label = DEFENSE_LABELS.get(candidate, candidate)
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        rf"Model & Baseline util & {_escape_tex(cand_label)} util & Security & Retention \\",
        r"\midrule",
    ]
    for row in models:
        lines.append(
            f"{_escape_tex(row.get('model_mode', ''))} "
            f"& {_pct(row.get('baseline_utility', 0))} "
            f"& {_pct(row.get(f'{candidate}_utility', 0))} "
            f"& {_pct(row.get(f'{candidate}_security', 0))} "
            f"& {_pct(row.get('utility_retention', 0))} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_m4_cross_model.tex", "\n".join(lines))


def fig_cross_model(cross_model: dict, out: Path) -> None:
    models = cross_model.get("models") or []
    if len(models) < 2:
        return
    candidate = cross_model.get("candidate", "bio_idea1_provenance_reflection_meta_full")
    labels = [m.get("model_mode", "?") for m in models]
    utils = [100 * float(m.get(f"{candidate}_utility", 0)) for m in models]
    secs = [100 * float(m.get(f"{candidate}_security", 0)) for m in models]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.bar(x - width / 2, utils, width, label="utility", color="#2F6F73")
    ax.bar(x + width / 2, secs, width, label="security", color="#C44E52", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 108)
    ax.set_title(f"M4 Cross-model {DEFENSE_LABELS.get(candidate, candidate)} on curated slice")
    ax.legend(loc="lower right")
    fig.savefig(out / "fig_m4_cross_model.png")
    plt.close(fig)


def table_live_baselines(paired_metrics: dict, out: Path) -> None:
    defenses = paired_metrics.get("defenses") or {}
    if not defenses:
        return
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Defense & $n$ & Utility & 95\% CI & Security \\",
        r"\midrule",
    ]
    ordered = [d for d in TABLE_DEFENSE_ORDER if d in defenses] + [
        d for d in defenses if d not in TABLE_DEFENSE_ORDER
    ]
    for defense in ordered:
        stats = defenses[defense]
        ci = stats["utility_ci"]
        ci_text = f"[{_pct(ci['ci_low'])}, {_pct(ci['ci_high'])}]"
        lines.append(
            f"{_escape_tex(DEFENSE_LABELS.get(defense, defense))} & {stats['n']} "
            f"& {_pct(stats['utility_mean'])} & {_escape_tex(ci_text)} "
            f"& {_pct(stats['security_mean'])} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_e5_live_baselines.tex", "\n".join(lines))


def table_multi_task_offline(rows: list[dict], out: Path) -> None:
    if not rows:
        return
    lines = [
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Task & Type & Utility & Security & Attack blocked \\",
        r"\midrule",
    ]
    for row in rows:
        blocked = "yes" if row.get("security_score", 0) >= 1 else "no"
        lines.append(
            f"{_escape_tex(row['suite'] + '/' + row['task_id'])} "
            f"& {_escape_tex(row['task_type'])} & {_pct(row['utility_score'])} "
            f"& {_pct(row['security_score'])} & {_escape_tex(blocked)} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    _write_tex(out / "table_e6_multi_task_offline.tex", "\n".join(lines))


def table_frontier(frontier: dict, out: Path) -> None:
    if not frontier:
        return
    lines = [
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Defense & Utility & Security \\",
        r"\midrule",
        f"{_escape_tex(DEFENSE_LABELS.get(frontier.get('anchor'), frontier.get('anchor', 'anchor')))} "
        f"& {_pct(frontier.get('anchor_utility', 0))} & {_pct(frontier.get('anchor_security', 0))} \\\\",
        f"{_escape_tex(DEFENSE_LABELS.get(frontier.get('candidate'), frontier.get('candidate', 'candidate')))} "
        f"& {_pct(frontier.get('candidate_utility', 0))} & {_pct(frontier.get('candidate_security', 0))} \\\\",
        r"\midrule",
        f"$\\Delta$ utility & {frontier.get('utility_delta_at_similar_security', 0) * 100:+.1f} & -- \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    _write_tex(out / "table_m2_frontier.tex", "\n".join(lines))


def write_artifact_guide(out: Path) -> None:
    guide = """# Paper Artifact Guide

## Main Text Recommended

1. `fig_e1_scheme_pareto.png`  
   Use as the main design-space figure. It shows the utility recovery sequence while security remains at 100%.

2. `table_e2_module_ablation.tex`  
   Prefer this three-line table over a large module chart. It ties each drop-one variant to the failure class (F1-F5).

3. `table_e5_live_baselines.tex` and `table_m2_significance.tex`  
   Prefer the baseline table for point estimates + CI; use the significance table for McNemar $p$-values vs `none`.

4. `fig_p0_task_defense_heatmap.png`  
   Use only if the text needs per-task failure locality. Otherwise place it in appendix.

## Appendix / Supporting

1. `table_e1_scheme_progression.tex`  
   Numeric companion to Figure E1.

2. `table_e6_multi_task_offline.tex` and `fig_e6_multi_task_offline.png`  
   Supports the multi-task fixture generalization claim.

3. `fig_e7_idea1_decomposition.png`  
   Supports the Idea1 vs Provenance decomposition.

4. `fig_e4_mechanism_taxonomy.png` and `fig_e4_mechanism_by_task.png`  
   Use when discussing mechanism-level trace analysis.

5. `table_m2_frontier.tex` / `fig_m2_tool_filter_frontier.png`  
   Use for the tool_filter frontier claim. Note the DeepSeek empty-completion caveat for tool_filter.

## Usually Skip From Main Text

`fig_m2_hv_scheme.png`, `fig_m2_hv_module.png`, and `fig_m2_utility_retention.png` are useful checks but visually less informative on this small curated slice.
"""
    (out / "README.md").write_text(guide, encoding="utf-8")


def merge_archive_mechanisms(summary: dict) -> dict:
    merged: Counter = Counter(summary.get("mechanism", {}).get("by_mechanism") or {})
    for entry in summary.get("mechanism_archive") or []:
        merged.update(entry.get("by_mechanism") or {})
    return dict(merged)


def generate_all(summary_path: Path, out_dir: Path, logdir: Path | None = None) -> None:
    _setup_style()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = _load_summary(summary_path)
    offline = summary.get("offline") or {}

    fig_scheme_pareto(offline.get("scheme_progression") or [], out_dir)
    fig_module_heatmap(
        offline.get("module_delta_vs_full") or [],
        out_dir,
        offline.get("module_failure_impact"),
    )
    fig_idea1_decomposition(offline.get("idea1_decomposition") or [], out_dir)
    fig_multi_task_offline(offline.get("multi_task_fixtures") or [], out_dir)
    table_scheme_progression(offline.get("scheme_progression") or [], out_dir)
    table_module_ablation(offline.get("module_failure_impact") or [], out_dir)
    table_multi_task_offline(offline.get("multi_task_fixtures") or [], out_dir)

    hv = offline.get("hypervolume") or {}
    fig_hypervolume(hv.get("scheme_progression") or {}, out_dir, "M2 Hypervolume — scheme stages", "fig_m2_hv_scheme.png")
    fig_hypervolume(hv.get("module_ablation") or {}, out_dir, "M2 Hypervolume — module ablation", "fig_m2_hv_module.png")

    live = summary.get("live") or {}
    if live.get("paired_metrics"):
        fig_live_defense_comparison(live["paired_metrics"], out_dir)
        fig_p1_baseline_comparison(live["paired_metrics"], out_dir)
        table_live_baselines(live["paired_metrics"], out_dir)
        table_significance(live["paired_metrics"], out_dir)
    if summary.get("cross_model"):
        table_cross_model(summary["cross_model"], out_dir)
        fig_cross_model(summary["cross_model"], out_dir)
    if live.get("frontier"):
        fig_tool_filter_frontier(live["frontier"], out_dir)
        table_frontier(live["frontier"], out_dir)
    if live.get("paired_rows"):
        fig_per_task_heatmap(live["paired_rows"], out_dir)

    mech = merge_archive_mechanisms(summary)
    if mech:
        fig_mechanism_bars(mech, out_dir)
    mech_eps = (summary.get("mechanism") or {}).get("episodes") or []
    if mech_eps:
        fig_mechanism_by_task_type(mech_eps, out_dir)

    # Write artifact manifests
    manifest = sorted(p.name for p in out_dir.glob("*.png"))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tables = sorted(p.name for p in out_dir.glob("*.tex"))
    (out_dir / "tables_manifest.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
    write_artifact_guide(out_dir)
    print(f"Wrote {len(manifest)} figures and {len(tables)} tables to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--logdir", type=Path, default=None)
    args = parser.parse_args()
    generate_all(args.summary, args.out, args.logdir)


if __name__ == "__main__":
    main()
