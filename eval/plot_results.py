#!/usr/bin/env python3
"""Generate AgentDojo benchmark + Idea1/Idea2 pipeline diagnostic figures."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "runs/agentdojo_upstream/benchmark_20260629_224640/report.json"
DEFAULT_LOGDIR = ROOT / "runs/agentdojo_upstream/benchmark_20260629_224640/logs"
DEFAULT_OUT = ROOT / "figures/agentdojo_20260630"

PAPER_DEFENSES = {
    "none",
    "tool_filter",
    "spotlighting_with_delimiting",
    "repeat_user_prompt",
}
BIO_DEFENSES = {"bio_idea1", "bio_idea2", "bio_idea2_v2", "bio_full"}
DEFENSE_LABELS = {
    "none": "none",
    "tool_filter": "tool_filter",
    "spotlighting_with_delimiting": "spotlighting",
    "repeat_user_prompt": "repeat_prompt",
    "bio_idea1": "bio_idea1",
    "bio_idea2": "bio_idea2",
    "bio_idea2_v2": "bio_idea2_v2",
    "bio_full": "bio_full",
}
SUITES = ("workspace", "travel", "banking", "slack")

WITHHELD_MARK = "withheld by BioHarness"
INFO_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")


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


def load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def combined_df(report: dict) -> pd.DataFrame:
    rows = []
    for defense, metrics in report.get("combined", {}).items():
        if "error" in metrics:
            continue
        rows.append(
            {
                "defense": defense,
                "label": DEFENSE_LABELS.get(defense, defense),
                "group": "BioHarness" if defense in BIO_DEFENSES else "Paper baseline",
                "utility": metrics["avg_utility_pct"],
                "security": metrics["avg_security_pct"],
                "asr": metrics.get("ASR_pct", 100 - metrics["avg_security_pct"]),
            }
        )
    return pd.DataFrame(rows)


def suite_df(report: dict) -> pd.DataFrame:
    rows = []
    for defense, suites in report.get("results", {}).items():
        for suite, metrics in suites.items():
            if not isinstance(metrics, dict) or "error" in metrics:
                continue
            rows.append(
                {
                    "defense": defense,
                    "label": DEFENSE_LABELS.get(defense, defense),
                    "group": "BioHarness" if defense in BIO_DEFENSES else "Paper baseline",
                    "suite": suite,
                    "utility": metrics.get("utility_pct", metrics.get("utility", 0) * 100),
                    "security": metrics.get("security_pct", metrics.get("security", 0) * 100),
                    "asr": metrics.get("ASR_pct", metrics.get("ASR", 0) * 100),
                }
            )
    return pd.DataFrame(rows)


def plot_utility_security_scatter(df: pd.DataFrame, out: Path, meta: dict) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    palette = {"Paper baseline": "#6b7280", "BioHarness": "#2563eb"}
    for group, gdf in df.groupby("group"):
        ax.scatter(
            gdf["utility"],
            gdf["security"],
            s=140,
            c=palette[group],
            label=group,
            edgecolors="white",
            linewidths=0.8,
            zorder=3,
        )
        for _, row in gdf.iterrows():
            ax.annotate(
                row["label"],
                (row["utility"], row["security"]),
                textcoords="offset points",
                xytext=(6, 4),
                fontsize=9,
            )
    ax.set_xlabel("Utility (%)")
    ax.set_ylabel("Security (%)")
    ax.set_title("AgentDojo: Utility vs Security trade-off")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.legend(loc="lower left")
    ax.text(
        0.02,
        0.02,
        f"{meta.get('model_name', '')} · {meta.get('attack', '')} · {meta.get('benchmark_version', '')}",
        transform=ax.transAxes,
        fontsize=9,
        color="#555",
    )
    fig.savefig(out / "01_utility_security_scatter.png")
    plt.close(fig)


def plot_grouped_bars(df: pd.DataFrame, out: Path) -> None:
    order = [
        "none",
        "spotlighting",
        "repeat_prompt",
        "tool_filter",
        "bio_idea2",
        "bio_idea2_v2",
        "bio_idea1",
        "bio_full",
    ]
    plot_df = df.set_index("label").reindex(order).reset_index()
    x = np.arange(len(plot_df))
    width = 0.35
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - width / 2, plot_df["utility"], width, label="Utility", color="#60a5fa")
    ax.bar(x + width / 2, plot_df["security"], width, label="Security", color="#34d399")
    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["label"], rotation=20, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Percent")
    ax.set_title("Combined metrics by defense")
    ax.legend()
    fig.savefig(out / "02_defense_grouped_bars.png")
    plt.close(fig)


def plot_security_heatmap(sdf: pd.DataFrame, out: Path) -> None:
    focus = sdf[sdf["defense"].isin(PAPER_DEFENSES | BIO_DEFENSES)]
    pivot = focus.pivot(index="label", columns="suite", values="security")
    pivot = pivot.reindex(columns=list(SUITES))
    fig, ax = plt.subplots(figsize=(8, 7))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap="YlGn",
        vmin=70,
        vmax=100,
        cbar_kws={"label": "Security (%)"},
        ax=ax,
    )
    ax.set_title("Security (%) by defense × suite")
    ax.set_xlabel("Suite")
    ax.set_ylabel("")
    fig.savefig(out / "03_security_heatmap_by_suite.png")
    plt.close(fig)


def plot_idea2_suites(sdf: pd.DataFrame, out: Path) -> None:
    subset = sdf[sdf["defense"].isin(["none", "bio_idea2", "bio_idea2_v2"])].copy()
    subset["defense"] = subset["defense"].map(
        {"none": "none", "bio_idea2": "idea2 (old)", "bio_idea2_v2": "idea2_v2"}
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharex=True)
    for ax, metric, title in zip(
        axes,
        ["utility", "security"],
        ["Utility by suite", "Security by suite"],
    ):
        sns.barplot(data=subset, x="suite", y=metric, hue="defense", ax=ax)
        ax.set_title(title)
        ax.set_ylim(0, 105)
        ax.set_xlabel("")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend_.remove()
    axes[1].legend_.remove()
    fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Idea2 evolution vs no defense", y=1.08)
    fig.savefig(out / "04_idea2_suite_comparison.png")
    plt.close(fig)


def _message_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content") or block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def scan_agentdojo_log(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    messages = data.get("messages") or []
    withheld = 0
    tool_info_visible = 0
    thread_info_visible = 0
    for msg in messages:
        text = _message_text(msg.get("content"))
        role = msg.get("role", "")
        if WITHHELD_MARK.lower() in text.lower():
            withheld += 1
        if role == "tool" and INFO_RE.search(text):
            tool_info_visible += 1
        if role in ("tool", "assistant", "user") and INFO_RE.search(text):
            thread_info_visible += 1
    attack_success = bool(data.get("security", False))  # AgentDojo: True = injection succeeded
    return {
        "utility": bool(data.get("utility", False)),
        "attack_success": attack_success,
        "defense_success": not attack_success,
        "withheld_events": withheld,
        "tool_withheld": withheld > 0,
        "tool_info_leak": tool_info_visible > 0,
        "thread_info_leak": thread_info_visible > 0,
    }


def scan_defense_logs(logdir: Path, defense: str) -> pd.DataFrame:
    rows = []
    base = logdir / defense
    if not base.exists():
        return pd.DataFrame()
    for path in base.rglob("tool_knowledge/*.json"):
        parts = path.parts
        suite = next((p for p in parts if p in SUITES), "unknown")
        stats = scan_agentdojo_log(path)
        if not stats:
            continue
        rows.append({"defense": defense, "suite": suite, **stats})
    return pd.DataFrame(rows)


def plot_agentdojo_mechanism(logdir: Path, out: Path) -> None:
    frames = []
    for defense in ("bio_idea1", "bio_idea2", "bio_idea2_v2", "bio_full"):
        df = scan_defense_logs(logdir, defense)
        if not df.empty:
            frames.append(df)
    if not frames:
        return
    all_df = pd.concat(frames, ignore_index=True)

    def classify(row) -> str:
        if row["tool_withheld"]:
            return "tool_withheld"
        if row["tool_info_leak"]:
            return "injection_visible_in_tool"
        if row["thread_info_leak"]:
            return "injection_visible_in_thread"
        return "clean_or_stripped"

    all_df["mechanism"] = all_df.apply(classify, axis=1)

    # Stacked bar: mechanism mix per defense × suite
    mix = (
        all_df.groupby(["defense", "suite", "mechanism"], observed=True)
        .size()
        .reset_index(name="count")
    )
    mix["pct"] = mix.groupby(["defense", "suite"])["count"].transform(lambda s: 100 * s / s.sum())
    g = sns.catplot(
        data=mix,
        kind="bar",
        x="suite",
        y="pct",
        hue="mechanism",
        col="defense",
        col_wrap=2,
        sharey=True,
        height=4,
        aspect=1.1,
        legend_out=True,
    )
    g.set_axis_labels("", "Share of episodes (%)")
    g.set_titles("{col_name}")
    g.fig.subplots_adjust(top=0.88)
    g.fig.suptitle("AgentDojo log diagnosis: mechanism mix by defense × suite")
    g.savefig(out / "05_agentdojo_mechanism_mix.png")
    plt.close(g.fig)

    # Outcome when attack succeeds vs mechanism
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharey=True)
    for ax, defense in zip(axes.flat, ("bio_idea1", "bio_idea2", "bio_idea2_v2", "bio_full")):
        sub = all_df[all_df["defense"] == defense]
        if sub.empty:
            ax.set_visible(False)
            continue
        outcome = sub.groupby("mechanism", observed=True)["attack_success"].mean().reset_index()
        outcome["defense_rate_pct"] = 100 * (1 - outcome["attack_success"])
        sns.barplot(data=outcome, x="mechanism", y="defense_rate_pct", ax=ax, color="#2563eb")
        ax.set_title(defense)
        ax.set_xticks(range(len(outcome)))
        ax.set_xticklabels(outcome["mechanism"], rotation=25, ha="right")
        ax.set_ylabel("Defense success rate (%)")
        ax.set_ylim(0, 105)
    fig.suptitle("Defense success rate by observed mechanism (AgentDojo logs)")
    fig.tight_layout()
    fig.savefig(out / "06_agentdojo_mechanism_success_rate.png")
    plt.close(fig)

    all_df.to_csv(out / "agentdojo_log_diagnosis.csv", index=False)


def load_jsonl_records(paths: list[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def load_jsonl_records(paths: list[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def _bool_col(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series(False, index=df.index)
    return df[name].fillna(False).astype(bool)


def classify_block_layer(row: pd.Series) -> str:
    """Scripted harness block attribution with Idea1 partition path."""
    fold_b = bool(row.get("fold_blocked", False))
    gate_b = bool(row.get("gate_blocked", False))
    harmful = bool(row.get("harmful", False))

    if fold_b and gate_b:
        return "fold+gate"
    if fold_b:
        return "fold_only"
    if gate_b:
        return "gate_only"
    if harmful:
        return "attack_escaped"
    return "partition_other"


LAYER_ORDER = ["fold_only", "gate_only", "fold+gate", "partition_other", "attack_escaped"]
LAYER_LABELS = {
    "fold_only": "Fold only",
    "gate_only": "Gate only",
    "fold+gate": "Fold+Gate",
    "partition_other": "Partition/other",
    "attack_escaped": "Attack escaped (ASR)",
}
LAYER_COLORS = {
    "fold_only": "#93c5fd",
    "gate_only": "#fca5a5",
    "fold+gate": "#c4b5fd",
    "partition_other": "#6ee7b7",
    "attack_escaped": "#d1d5db",
}


def _prepare_attack_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df[df["label"] == "attack"].copy()
    for col in ("fold_blocked", "gate_blocked", "blocked", "harmful"):
        out[col] = _bool_col(out, col)
    out["layer"] = out.apply(classify_block_layer, axis=1)
    return out


def _layer_rates_by_attack(df: pd.DataFrame) -> pd.DataFrame:
    """Per attack_type: fold/gate/partition/asr rates from jsonl records."""
    atk = _prepare_attack_df(df)
    if atk.empty:
        return pd.DataFrame()
    rows = []
    for attack_type, grp in atk.groupby("attack_type", observed=True):
        n = len(grp)
        rows.append(
            {
                "attack_type": attack_type,
                "n": n,
                "fold_block_rate": 100 * grp["fold_blocked"].mean(),
                "gate_block_rate": 100 * grp["gate_blocked"].mean(),
                "partition_rate": 100 * (grp["layer"] == "partition_other").mean(),
                "asr_pct": 100 * grp["harmful"].mean(),
                "block_rate": 100 * grp["blocked"].mean(),
            }
        )
    return pd.DataFrame(rows)


def _scripted_jsonl_sources() -> dict[str, list[Path]]:
    runs = ROOT / "runs"
    return {
        "idea1_only": [
            runs / "exp_b_channel_20260627_211226/idea1_only_results.jsonl",
            runs / "exp_c3_tool_injection_20260628_231246/idea1_only_results.jsonl",
            runs / "factorial_2x2_20260627_211226/idea1_only_results.jsonl",
        ],
        "idea2_only": sorted(runs.glob("exp_c*_20260628_231246/idea2_only_results.jsonl"))
        + [runs / "exp_a_shuffle_20260628_231040/idea2_only_results.jsonl"],
        "full": [
            runs / "factorial_2x2_20260627_211226/full_results.jsonl",
            runs / "exp_a_shuffle_20260628_231040/full_results.jsonl",
        ],
    }


def _layer_distribution(df: pd.DataFrame) -> pd.DataFrame:
    atk = _prepare_attack_df(df)
    if atk.empty:
        return pd.DataFrame()
    dist = atk["layer"].value_counts().reindex(LAYER_ORDER, fill_value=0)
    total = max(int(dist.sum()), 1)
    return pd.DataFrame(
        {"layer": dist.index, "count": dist.values, "pct": 100 * dist.values / total}
    )


def plot_scripted_layer_diagnostic(out: Path) -> None:
    sources = _scripted_jsonl_sources()

    idea2_df = load_jsonl_records(sources["idea2_only"])
    if not idea2_df.empty:
        idea2_df = _prepare_attack_df(idea2_df)
        layer = (
            idea2_df.groupby(["attack_type", "layer"], observed=True)
            .size()
            .reset_index(name="count")
        )
        layer["pct"] = layer.groupby("attack_type")["count"].transform(lambda s: 100 * s / s.sum())
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(
            data=layer,
            x="attack_type",
            y="pct",
            hue="layer",
            hue_order=LAYER_ORDER,
            ax=ax,
            palette=[LAYER_COLORS[k] for k in LAYER_ORDER],
        )
        ax.set_title("Idea2 scripted (C1–C6 + exp_a): block layer by attack type")
        ax.set_ylabel("Share of attack samples (%)")
        ax.set_xlabel("Attack dataset")
        ax.tick_params(axis="x", rotation=25)
        ax.legend(title="Layer", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
        fig.savefig(out / "07_idea2_scripted_block_layers.png")
        plt.close(fig)

    idea1_df = load_jsonl_records(sources["idea1_only"])
    if not idea1_df.empty:
        idea1_df = _prepare_attack_df(idea1_df)
        layer = (
            idea1_df.groupby(["attack_type", "layer"], observed=True)
            .size()
            .reset_index(name="count")
        )
        layer["pct"] = layer.groupby("attack_type")["count"].transform(lambda s: 100 * s / s.sum())
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(
            data=layer,
            x="attack_type",
            y="pct",
            hue="layer",
            hue_order=LAYER_ORDER,
            ax=ax,
            palette=[LAYER_COLORS[k] for k in LAYER_ORDER],
        )
        ax.set_title("Idea1 scripted (channel + tool injection + factorial): block layer")
        ax.set_ylabel("Share of attack samples (%)")
        ax.set_xlabel("Attack dataset")
        ax.legend(title="Layer", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
        fig.savefig(out / "08_idea1_scripted_block_layers.png")
        plt.close(fig)

    # Fig 09 — fold/gate/partition rates computed from jsonl (fixes Idea1 blank panel)
    rate_rows = []
    for cfg, paths in sources.items():
        if cfg == "full":
            continue
        df = load_jsonl_records(paths)
        rates = _layer_rates_by_attack(df)
        if rates.empty:
            continue
        rates["config"] = cfg
        rate_rows.append(rates)
    if rate_rows:
        rates_df = pd.concat(rate_rows, ignore_index=True)
        melt = rates_df.melt(
            id_vars=["config", "attack_type", "n"],
            value_vars=["fold_block_rate", "gate_block_rate", "partition_rate"],
            var_name="metric",
            value_name="rate_pct",
        )
        melt["metric"] = melt["metric"].str.replace("_rate", "").str.replace("_block", "")
        metric_labels = {
            "fold": "fold",
            "gate": "gate",
            "partition": "partition",
        }
        melt["metric"] = melt["metric"].map(metric_labels).fillna(melt["metric"])
        fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
        for ax, cfg, title in zip(
            axes,
            ["idea1_only", "idea2_only"],
            ["Idea1: fold / gate / partition by attack (jsonl)", "Idea2: fold / gate / partition by attack (jsonl)"],
        ):
            sub = melt[melt["config"] == cfg]
            if sub.empty:
                ax.text(0.5, 0.5, "No jsonl data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(title)
                continue
            sns.barplot(data=sub, x="attack_type", y="rate_pct", hue="metric", ax=ax)
            ax.set_title(title)
            ax.set_ylabel("Rate on attacks (%)")
            ax.tick_params(axis="x", rotation=25)
            ax.set_ylim(0, 105)
        handles, labels = axes[0].get_legend_handles_labels()
        if axes[0].legend_:
            axes[0].legend_.remove()
        if axes[1].legend_:
            axes[1].legend_.remove()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.02))
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        fig.savefig(out / "09_idea1_idea2_fold_vs_gate_by_attack.png")
        plt.close(fig)
        rates_df.to_csv(out / "scripted_layer_rates_by_attack.csv", index=False)


def plot_pipeline_funnel(out: Path) -> None:
    """Funnel with partition/other separate from true ASR escapes."""
    sources = _scripted_jsonl_sources()
    specs = [
        ("Idea1", sources["idea1_only"]),
        ("Idea2", sources["idea2_only"]),
        ("Full", sources["full"]),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    summary_rows = []
    for ax, (name, paths) in zip(axes, specs):
        dist = _layer_distribution(load_jsonl_records(paths))
        if dist.empty:
            ax.set_visible(False)
            continue
        labels = [LAYER_LABELS.get(k, k) for k in dist["layer"]]
        colors = [LAYER_COLORS.get(k, "#ccc") for k in dist["layer"]]
        vals = dist["count"].tolist()
        total = max(int(dist["count"].sum()), 1)
        ax.barh(labels, vals, color=colors)
        for i, (v, pct) in enumerate(zip(vals, dist["pct"])):
            if v > 0:
                ax.text(v + max(total * 0.01, 0.3), i, f"{int(v)} ({pct:.0f}%)", va="center", fontsize=9)
        ax.set_title(f"{name} scripted (n={total})")
        ax.set_xlabel("Count")
        ax.invert_yaxis()
        for _, row in dist.iterrows():
            summary_rows.append({"config": name, **row.to_dict()})
    fig.suptitle("Pipeline stage attribution (partition/other ≠ attack escape)")
    fig.tight_layout()
    fig.savefig(out / "10_pipeline_stage_funnel.png")
    plt.close(fig)
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(out / "pipeline_funnel_summary.csv", index=False)


def plot_synergy_table(report: dict, out: Path) -> None:
    """Full vs Idea1 vs Idea2: AgentDojo + scripted factorial."""
    runs = ROOT / "runs"
    factorial_path = runs / "factorial_2x2_20260627_211226/report.json"

    # AgentDojo bio subset
    agent_rows = []
    for defense in ("bio_idea1", "bio_idea2", "bio_idea2_v2", "bio_full"):
        m = report.get("combined", {}).get(defense, {})
        if not m or "error" in m:
            continue
        agent_rows.append(
            {
                "source": "AgentDojo",
                "config": defense,
                "utility_pct": m.get("avg_utility_pct", 0),
                "security_pct": m.get("avg_security_pct", 0),
                "asr_pct": m.get("ASR_pct", 0),
                "n_pairs": "949×4 suites",
            }
        )
    agent_df = pd.DataFrame(agent_rows)

    # Scripted factorial summaries
    script_rows = []
    if factorial_path.exists():
        fac = json.loads(factorial_path.read_text(encoding="utf-8"))
        for item in fac.get("summaries", []):
            cfg = item.get("config", "")
            if cfg not in ("idea1_only", "idea2_only", "full", "baseline_1"):
                continue
            script_rows.append(
                {
                    "source": "scripted factorial",
                    "config": cfg,
                    "utility_pct": round(100 * item.get("task_completion_rate", 0), 2),
                    "security_pct": round(100 * (1 - item.get("asr", 0)), 2),
                    "asr_pct": round(100 * item.get("asr", 0), 2),
                    "block_rate_pct": round(100 * item.get("block_rate", 0), 2),
                    "n_pairs": item.get("attacks", "?"),
                }
            )
    script_df = pd.DataFrame(script_rows)

    combined = pd.concat([agent_df, script_df], ignore_index=True)
    combined.to_csv(out / "11_synergy_table.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: AgentDojo ASR/Security for bio configs
    if not agent_df.empty:
        ax = axes[0]
        x = np.arange(len(agent_df))
        w = 0.35
        ax.bar(x - w / 2, agent_df["utility_pct"], w, label="Utility", color="#60a5fa")
        ax.bar(x + w / 2, agent_df["security_pct"], w, label="Security", color="#34d399")
        ax.set_xticks(x)
        ax.set_xticklabels(agent_df["config"], rotation=20, ha="right")
        ax.set_ylim(0, 105)
        ax.set_title("AgentDojo: bio_idea1 / idea2 / v2 / full")
        ax.set_ylabel("Percent")
        ax.legend()

    # Right: factorial ASR by config + attack type for idea1/2/full
    ax = axes[1]
    if factorial_path.exists():
        fac = json.loads(factorial_path.read_text(encoding="utf-8"))
        atk_rows = []
        for item in fac.get("by_attack_type", {}).values():
            if item.get("config") not in ("idea1_only", "idea2_only", "full"):
                continue
            atk_rows.append(
                {
                    "config": item["config"],
                    "attack_type": item["attack_type"],
                    "asr_pct": 100 * item.get("asr", 0),
                }
            )
        atk_df = pd.DataFrame(atk_rows)
        if not atk_df.empty:
            sns.barplot(data=atk_df, x="attack_type", y="asr_pct", hue="config", ax=ax)
            ax.set_title("Scripted factorial: ASR by attack (lower is better)")
            ax.set_ylabel("ASR (%)")
            ax.tick_params(axis="x", rotation=25)
            ax.legend(title="Config", fontsize=8)
    fig.suptitle("Idea1 + Idea2 synergy: AgentDojo vs scripted factorial")
    fig.tight_layout()
    fig.savefig(out / "11_synergy_agentdojo_and_factorial.png")
    plt.close(fig)

    # Table figure
    if not combined.empty:
        fig, ax = plt.subplots(figsize=(12, max(2, 0.45 * len(combined) + 1)))
        ax.axis("off")
        cols = [c for c in combined.columns if c in combined.columns]
        table = ax.table(
            cellText=combined[cols].values,
            colLabels=cols,
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.4)
        ax.set_title("Synergy summary table", pad=20)
        fig.savefig(out / "11_synergy_table.png")
        plt.close(fig)


def write_readme(out: Path, meta: dict) -> None:
    text = f"""# AgentDojo + BioHarness figures

Generated from `{meta.get('report_path', '')}`.

## Main benchmark
- `01_utility_security_scatter.png` — Utility vs Security (combined)
- `02_defense_grouped_bars.png` — Utility & Security bars
- `03_security_heatmap_by_suite.png` — Security by defense × suite
- `04_idea2_suite_comparison.png` — none vs idea2 vs idea2_v2 per suite

## Diagnostics
- `05_agentdojo_mechanism_mix.png` — log-mined mechanism mix on AgentDojo
- `06_agentdojo_mechanism_success_rate.png` — defense success by mechanism
- `07_idea2_scripted_block_layers.png` — Idea2 C1–C6 fold/gate/escape
- `08_idea1_scripted_block_layers.png` — Idea1 channel/tool injection layers
- `09_idea1_idea2_fold_vs_gate_by_attack.png` — fold/gate/partition rates from jsonl
- `10_pipeline_stage_funnel.png` — funnel (partition/other vs true ASR escape)
- `11_synergy_agentdojo_and_factorial.png` — full vs idea1 vs idea2 synergy
- `11_synergy_table.png` / `11_synergy_table.csv` — summary table

Model: {meta.get('model_name')} | Attack: {meta.get('attack')} | Version: {meta.get('benchmark_version')}
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot AgentDojo benchmark + diagnostics")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--logdir", type=Path, default=DEFAULT_LOGDIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    _setup_style()
    args.out.mkdir(parents=True, exist_ok=True)

    report = load_report(args.report)
    meta = {
        "report_path": str(args.report),
        "model_name": report.get("model_name"),
        "attack": report.get("attack"),
        "benchmark_version": report.get("benchmark_version"),
    }

    cdf = combined_df(report)
    sdf = suite_df(report)

    plot_utility_security_scatter(cdf, args.out, meta)
    plot_grouped_bars(cdf, args.out)
    plot_security_heatmap(sdf, args.out)
    plot_idea2_suites(sdf, args.out)
    plot_agentdojo_mechanism(args.logdir, args.out)
    plot_scripted_layer_diagnostic(args.out)
    plot_pipeline_funnel(args.out)
    plot_synergy_table(report, args.out)
    write_readme(args.out, meta)

    print(f"Figures written to {args.out}")


if __name__ == "__main__":
    main()
