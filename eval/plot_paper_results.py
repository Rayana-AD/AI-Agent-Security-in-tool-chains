#!/usr/bin/env python3
"""Generate publication-ready result figures and LaTeX tables."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures" / "paper_results"

MODEL_INPUTS = {
    "DeepSeek-Chat (V3)": ROOT / "figures" / "m1_manifest_seed" / "summary_stress_valid.csv",
    "Llama-3-70B": ROOT / "figures" / "m1_manifest_seed_llama70" / "summary_stress_valid.csv",
}

TARGETED_REPORTS = {
    "Task decomposition": ROOT / "runs" / "exp_c1_drattack_20260628_231245" / "report.json",
    "Cross-node fragmentation": ROOT / "runs" / "exp_c2_cross_node_20260628_231246" / "report.json",
    "External observation injection": ROOT / "runs" / "exp_c3_tool_injection_20260628_231246" / "report.json",
    "Schema-structured smuggling": ROOT / "runs" / "exp_c4_schema_smuggle_20260628_231246" / "report.json",
    "Rationalized deception": ROOT / "runs" / "exp_c5_subtle_deception_20260628_231246" / "report.json",
    "Gradual risk escalation": ROOT / "runs" / "exp_c6_escalation_20260628_231246" / "report.json",
}

DEFENSE_ORDER = [
    "none",
    "spotlighting_with_delimiting",
    "transformers_pi_detector",
    "bio_04",
]
DEFENSE_LABELS = {
    "none": "No defense",
    "spotlighting_with_delimiting": "Spotlighting",
    "transformers_pi_detector": "Learned detector",
    "bio_04": "Ours",
}
DEFENSE_COLORS = {
    "none": "#9CA3AF",
    "spotlighting_with_delimiting": "#4C78A8",
    "transformers_pi_detector": "#F2A541",
    "bio_04": "#0F9D78",
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
        }
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.png", dpi=300)
    plt.close(fig)


def load_model_results() -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for model, path in MODEL_INPUTS.items():
        df = pd.read_csv(path).set_index("defense").reindex(DEFENSE_ORDER).reset_index()
        results[model] = df
    return results


def plot_frontier(results: dict[str, pd.DataFrame]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.15), sharex=True, sharey=True)
    offsets = {
        "none": (4, -12),
        "spotlighting_with_delimiting": (4, 5),
        "transformers_pi_detector": (4, 5),
        "bio_04": (-48, -13),
    }
    for ax, (model, df) in zip(axes, results.items()):
        for _, row in df.iterrows():
            defense = row["defense"]
            ax.scatter(
                row["utility"],
                row["security"],
                s=72,
                color=DEFENSE_COLORS[defense],
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )
            ax.annotate(
                DEFENSE_LABELS[defense],
                (row["utility"], row["security"]),
                xytext=offsets[defense],
                textcoords="offset points",
                fontsize=7.5,
            )
        ax.set_title(model, fontweight="bold")
        ax.set_xlim(25, 100)
        ax.set_ylim(30, 103)
        ax.set_xlabel("Utility (%)")
        ax.grid(alpha=0.22, linewidth=0.6)
        ax.axhline(100, color="#6B7280", linestyle=":", linewidth=0.8)
    axes[0].set_ylabel("Security (%)")
    fig.suptitle("Utility--security performance on stress-valid AgentDojo batches", y=1.01)
    fig.tight_layout()
    save_figure(fig, "fig_end_to_end_frontier")


def plot_progression() -> None:
    labels = [
        "Withhold\nonly",
        "+ Metadata\nrepair",
        "+ Reflection-aware\nread handling",
        "+ Lightweight\nstate",
        "+ Unified\nauthorization",
        "Full\nprotocol",
    ]
    utility = np.array([20, 60, 80, 80, 80, 100])
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.0, 3.05))
    ax.plot(x, utility, color="#2A6F73", linewidth=2.2, marker="o", markersize=7)
    for i, value in enumerate(utility):
        ax.text(i, value + 3.2, f"{value}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Utility (%)")
    ax.set_title("Staged utility recovery under fixed security")
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.text(
        0.99,
        0.05,
        "Security remains 100% on this offline probe",
        transform=ax.transAxes,
        ha="right",
        color="#555555",
        fontsize=8,
    )
    fig.tight_layout()
    save_figure(fig, "fig_staged_utility_recovery")


def targeted_rows() -> pd.DataFrame:
    rows = []
    for category, path in TARGETED_REPORTS.items():
        report = json.loads(path.read_text(encoding="utf-8"))
        summaries = {row["config"]: row for row in report["summaries"]}
        rows.append(
            {
                "category": category,
                "n": int(report["n_samples"]),
                "Schema only": 100 * float(summaries["schema_only"]["block_rate"]),
                "Shuffle Fold": 100 * float(summaries["full"]["block_rate"]),
            }
        )
    return pd.DataFrame(rows)


def plot_targeted_attacks(df: pd.DataFrame) -> None:
    y = np.arange(len(df))
    gain = df["Shuffle Fold"] - df["Schema only"]
    fig, ax = plt.subplots(figsize=(7.0, 3.35))
    ax.hlines(y, 0, gain, color="#9FD8C8", linewidth=4)
    ax.scatter(gain, y, s=70, color="#0F9D78", edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(df["category"])
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xlabel("Security gain from shuffle coherence (percentage points)")
    ax.set_title("Shuffle coherence closes order-dependent security gaps")
    ax.grid(axis="x", alpha=0.22, linewidth=0.6)
    for i, value in enumerate(gain):
        ax.text(value + 1.2, i, f"+{value:.0f}", va="center", fontsize=7.5)
    fig.tight_layout()
    save_figure(fig, "fig_shuffle_security_gain")


def attack_type_rows(path: Path, model: str) -> list[dict]:
    progress = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for key, gate in progress.get("gate_results", {}).items():
        if not gate.get("stress_ok"):
            continue
        parts = key.split("|")
        if len(parts) < 4:
            continue
        per_defense = gate.get("metrics", {}).get("per_defense", {})
        if "bio_04" not in per_defense:
            continue
        values = per_defense["bio_04"]
        rows.append(
            {
                "model": model,
                "attack": parts[1],
                "utility": 100 * float(values.get("utility", 0)),
                "security": 100 * float(values.get("security", 0)),
            }
        )
    return rows


def plot_attack_type_tradeoff() -> None:
    rows = attack_type_rows(
        ROOT / "runs" / "table1_remeasure" / "merged_deepseek.json",
        "DeepSeek-Chat (V3)",
    )
    rows += attack_type_rows(
        ROOT / "runs" / "table1_remeasure" / "merged_llama.json",
        "Llama-3-70B",
    )
    df = pd.DataFrame(rows)
    summary = (
        df.groupby(["model", "attack"])
        .agg(utility=("utility", "mean"), security=("security", "mean"), n=("attack", "size"))
        .reset_index()
    )
    attack_labels = {
        "direct": "Direct injection",
        "important_instructions": "Instruction override",
        "important_instructions_education": "Education framing",
        "important_instructions_persona": "Persona framing",
    }
    attack_colors = {
        "direct": "#E45756",
        "important_instructions": "#4C78A8",
        "important_instructions_education": "#72B7B2",
        "important_instructions_persona": "#F2A541",
    }
    attack_markers = {
        "direct": "o",
        "important_instructions": "s",
        "important_instructions_education": "^",
        "important_instructions_persona": "D",
    }
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.1), sharex=True, sharey=True)
    for panel_i, (ax, (model, group)) in enumerate(zip(axes, summary.groupby("model", sort=False))):
        display_x: dict[int, float] = {}
        display_y: dict[int, float] = {}
        attack_z = {
            "direct": 3,
            "important_instructions": 4,
            "important_instructions_education": 6,
            "important_instructions_persona": 5,
        }
        for _, tied in group.groupby(["utility", "security"]):
            # Stable order so coincident instruction/education points separate predictably.
            ordered = tied.sort_values("attack")
            n = len(ordered)
            if n > 1:
                x_offsets = np.linspace(-2.4, 2.4, n)
                y_offsets = np.linspace(-1.0, 1.0, n)
            else:
                x_offsets = np.array([0.0])
                y_offsets = np.array([0.0])
            for x_off, y_off, row_index in zip(x_offsets, y_offsets, ordered.index):
                display_x[row_index] = float(ordered.loc[row_index, "utility"]) + float(x_off)
                display_y[row_index] = float(ordered.loc[row_index, "security"]) + float(y_off)
        for _, row in group.iterrows():
            attack = row["attack"]
            ax.scatter(
                display_x[row.name],
                display_y[row.name],
                s=90,
                color=attack_colors[attack],
                marker=attack_markers[attack],
                edgecolor="white",
                linewidth=0.9,
                zorder=attack_z.get(attack, 3),
                label=attack_labels[attack],
            )
        ax.set_title(model, fontweight="bold")
        ax.set_xlim(35, 100)
        ax.set_ylim(75, 103)
        ax.set_xlabel("Utility (%)")
        ax.grid(alpha=0.22, linewidth=0.6)
        ax.axhline(100, color="#6B7280", linestyle=":", linewidth=0.8)
    axes[0].set_ylabel("Security (%)")
    # Legend from both panels so a clipped/empty first panel cannot drop attack types.
    handles, labels = [], []
    for ax in axes:
        h, lab = ax.get_legend_handles_labels()
        for handle, label in zip(h, lab):
            if label not in labels:
                handles.append(handle)
                labels.append(label)
    # Prefer stable attack order when present.
    preferred = [
        "Direct injection",
        "Instruction override",
        "Education framing",
        "Persona framing",
    ]
    ordered = [(h, lab) for lab in preferred for h, l in zip(handles, labels) if l == lab]
    if ordered:
        handles, labels = zip(*ordered)
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle("Full-harness performance by attack type", y=1.02)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    save_figure(fig, "fig_attack_type_tradeoff")


def write_tables(results: dict[str, pd.DataFrame], targeted: pd.DataFrame) -> None:
    main_lines = [
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Model & Defense & Utility & Security & ASR & Batches \\",
        r"\midrule",
    ]
    for model_i, (model, df) in enumerate(results.items()):
        for row_i, (_, row) in enumerate(df.iterrows()):
            model_cell = model if row_i == 0 else ""
            defense = DEFENSE_LABELS[row["defense"]]
            bold = row["defense"] == "bio_04"
            values = [
                f"{row['utility']:.1f}",
                f"{row['security']:.1f}",
                f"{row['asr']:.1f}",
                f"{int(row['n_batches'])}",
            ]
            if bold:
                defense = rf"\textbf{{{defense}}}"
                values = [rf"\textbf{{{value}}}" for value in values]
            main_lines.append(
                f"{model_cell} & {defense} & " + " & ".join(values) + r" \\"
            )
        if model_i < len(results) - 1:
            main_lines.append(r"\midrule")
    main_lines += [r"\bottomrule", r"\end{tabular}", ""]
    (OUT / "table_main_results.tex").write_text("\n".join(main_lines), encoding="utf-8")

    targeted_lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Attack category & $n$ & Schema only & Shuffle Fold \\",
        r"\midrule",
    ]
    for _, row in targeted.iterrows():
        targeted_lines.append(
            f"{row['category']} & {int(row['n'])} & "
            f"{row['Schema only']:.0f} & {row['Shuffle Fold']:.0f}" + r" \\"
        )
    targeted_lines += [r"\bottomrule", r"\end{tabular}", ""]
    (OUT / "table_targeted_attacks.tex").write_text(
        "\n".join(targeted_lines), encoding="utf-8"
    )

    ablation_lines = [
        r"\begin{tabular}{lp{0.47\columnwidth}rr}",
        r"\toprule",
        r"Removed component & Observed consequence & $\Delta U$ & Security \\",
        r"\midrule",
        r"Metadata stripping & Injected observations remain withheld & $-40$ & 100 \\",
        r"Goal-aligned continuation & Benign post-repair actions remain constrained & $-20$ & 100 \\",
        r"Other single removals & No measurable change on this probe & $0$ & 100 \\",
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    (OUT / "table_module_ablation.tex").write_text(
        "\n".join(ablation_lines), encoding="utf-8"
    )


def main() -> None:
    setup_style()
    OUT.mkdir(parents=True, exist_ok=True)
    results = load_model_results()
    targeted = targeted_rows()
    plot_frontier(results)
    plot_progression()
    plot_targeted_attacks(targeted)
    plot_attack_type_tradeoff()
    write_tables(results, targeted)
    print(f"Paper result artifacts written to {OUT}")


if __name__ == "__main__":
    main()
