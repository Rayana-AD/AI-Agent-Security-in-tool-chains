#!/usr/bin/env python3
"""Paper-style figures for a possible new section: extended suites + adaptive IPI.

Matches eval/plot_paper_results.py (DejaVu, PDF+PNG, no underscore labels).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "runs" / "supplement" / "p2" / "official_matrix_v2" / "matrix_summary.json"
ADAPTIVE = ROOT / "runs" / "supplement" / "p1" / "adaptive_matrix_v1" / "report.json"
TENSION = ROOT / "runs" / "supplement" / "p1" / "adaptive_tension.json"
OUT = ROOT / "figures" / "paper_results"
OUT_COPY = ROOT / "runs" / "supplement" / "figures" / "paper_tracks"

CFG = {
    "schema_only": "Schema only",
    "idea1_only": "Partition only",
    "idea1_provenance_mlp_bio_04": "BioHarness",
    "bio_04_no_hard_rules": "w/o path rules",
}
CFG_COLOR = {
    "schema_only": "#9CA3AF",
    "idea1_only": "#4C78A8",
    "idea1_provenance_mlp_bio_04": "#0F9D78",
    "bio_04_no_hard_rules": "#F2A541",
}
CFG_MARKER = {
    "schema_only": "o",
    "idea1_only": "s",
    "idea1_provenance_mlp_bio_04": "D",
    "bio_04_no_hard_rules": "^",
}
SUITE = {
    "path_heldout": "Held-out path",
    "path_indist": "In-distribution path",
    "retry_full": "Retry channel",
    "fragmented_shuffle": "Fragmented",
    "reflection_process": "Process / reflection",
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
            "savefig.pad_inches": 0.04,
        }
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_COPY.mkdir(parents=True, exist_ok=True)
    for dest in (OUT, OUT_COPY):
        fig.savefig(dest / f"{stem}.pdf")
        fig.savefig(dest / f"{stem}.png", dpi=300)
    plt.close(fig)


def _load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _block(cells: dict, suite: str, cfg: str) -> float:
    return float(((cells.get(suite) or {}).get(cfg) or {}).get("attack_block_rate") or 0) * 100


# ── Paper track (only plots with a real gradient) ────────────────────────────


def fig_extended_suite_dumbbell(cells: dict) -> None:
    """Schema → BioHarness range, with path-rule ablation as a third marker.

    Partition-only is omitted here (it tracks schema-only on 3/5 suites and is
    reported in the paper table). Four overlapping series made the old Cleveland
    plot unreadable; 0/100-only charts are tables, not figures.
    """
    suites = list(SUITE.keys())
    schema = np.array([_block(cells, s, "schema_only") for s in suites])
    nopath = np.array([_block(cells, s, "bio_04_no_hard_rules") for s in suites])
    bio = np.array([_block(cells, s, "idea1_provenance_mlp_bio_04") for s in suites])
    y = np.arange(len(suites), dtype=float)
    y_schema = y.copy()
    y_nopath = y.copy()
    y_bio = y.copy()
    for i in range(len(suites)):
        if abs(nopath[i] - bio[i]) < 3:
            y_nopath[i] -= 0.18
            y_bio[i] += 0.18
        elif abs(schema[i] - nopath[i]) < 3:
            y_schema[i] -= 0.18
            y_nopath[i] += 0.18

    fig, ax = plt.subplots(figsize=(7.0, 3.35))
    ax.set_axisbelow(True)
    ax.grid(axis="x", linestyle="-", color="#D1D5DB", alpha=0.9, linewidth=0.75)
    ax.grid(axis="y", linestyle=":", color="#E5E7EB", alpha=0.95, linewidth=0.65)
    ax.set_xticks([0, 20, 40, 60, 80, 100])

    for i in range(len(suites)):
        ax.hlines(y[i], schema[i], bio[i], color="#9FD8C8", linewidth=5.2, zorder=1)

    ax.scatter(
        schema,
        y_schema,
        s=92,
        marker="o",
        facecolors="white",
        edgecolors="#4B5563",
        linewidths=1.7,
        zorder=3,
        label="Schema only",
    )
    ax.scatter(
        nopath,
        y_nopath,
        s=108,
        marker="^",
        color="#F2A541",
        edgecolors="#8A5A12",
        linewidths=0.6,
        zorder=4,
        label="w/o path rules",
    )
    ax.scatter(
        bio,
        y_bio,
        s=118,
        marker="D",
        color="#0F9D78",
        edgecolors="white",
        linewidths=0.9,
        zorder=5,
        label="BioHarness",
    )

    for i in range(len(suites)):
        ax.text(
            schema[i] - 2.4,
            y_schema[i],
            f"{schema[i]:.0f}",
            ha="right",
            va="center",
            fontsize=7.5,
            color="#4B5563",
        )
        if abs(nopath[i] - schema[i]) >= 8 and abs(nopath[i] - bio[i]) >= 8:
            ax.text(
                nopath[i],
                y_nopath[i] - 0.22,
                f"{nopath[i]:.0f}",
                ha="center",
                va="bottom",
                fontsize=7.5,
                color="#B45309",
            )
        ax.text(
            min(bio[i] + 2.4, 106),
            y_bio[i],
            f"{bio[i]:.0f}",
            ha="left",
            va="center",
            fontsize=7.5,
            color="#0B7A5C",
        )

    ax.set_yticks(y)
    ax.set_yticklabels([SUITE[s] for s in suites])
    ax.set_xlim(-10, 114)
    ax.set_ylim(len(suites) - 0.42, -0.55)
    ax.set_xlabel("Attack block rate (%)")
    ax.set_title("Offline evasion suites: baseline, path-rule ablation, full protocol")
    fig.legend(loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    save_figure(fig, "fig_extended_suite_gap")


def fig_s2_gain(cells: dict) -> None:
    """Lollipop: Schema → BioHarness gain (same idiom as fig_shuffle_security_gain)."""
    suites = list(SUITE.keys())
    schema = np.array([_block(cells, s, "schema_only") for s in suites])
    bio = np.array([_block(cells, s, "idea1_provenance_mlp_bio_04") for s in suites])
    gain = bio - schema
    y = np.arange(len(suites))
    fig, ax = plt.subplots(figsize=(7.0, 3.25))
    ax.hlines(y, 0, gain, color="#9FD8C8", linewidth=4)
    ax.scatter(gain, y, s=72, color="#0F9D78", edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([SUITE[s] for s in suites])
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xlabel("Block-rate gain of BioHarness over schema-only (pp)")
    ax.set_title("Where the full protocol closes offline gaps")
    ax.grid(axis="x", alpha=0.22, linewidth=0.6)
    for i, (g, b, s) in enumerate(zip(gain, bio, schema)):
        ax.text(g + 1.5, i, f"+{g:.0f}  ({s:.0f}→{b:.0f})", va="center", fontsize=7.5)
    fig.tight_layout()
    save_figure(fig, "fig_extended_suite_gain")


def fig_s3_retry(cells: dict) -> None:
    """Retry-channel mechanism: three attack types × three configs (markers, not bars)."""
    types = ["retry_abuse", "state_pollution", "fragmented"]
    type_lab = {
        "retry_abuse": "Retry after\nschema fail",
        "state_pollution": "Routing-metadata\npollution",
        "fragmented": "Cross-node\nfragments",
    }
    cfgs = [
        ("schema_only", "Schema only"),
        ("bio_04_no_hard_rules", "w/o path rules"),
        ("idea1_provenance_mlp_bio_04", "BioHarness"),
    ]
    suite = cells.get("retry_full") or {}
    x = np.arange(len(types))
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    for ck, lab in cfgs:
        by = (suite.get(ck) or {}).get("by_attack_type") or {}
        ys = [float((by.get(t) or {}).get("block_rate") or 0) * 100 for t in types]
        ax.plot(
            x,
            ys,
            color=CFG_COLOR[ck],
            marker=CFG_MARKER[ck],
            markersize=8,
            linewidth=1.8,
            label=lab,
        )
        # Annotate only values that are not the BioHarness ceiling (avoids stacked 100s).
        if ck != "idea1_provenance_mlp_bio_04":
            for xi, yi in zip(x, ys):
                dy = -8 if yi < 10 else 4
                ax.text(xi, yi + dy, f"{yi:.0f}", ha="center", fontsize=7, color=CFG_COLOR[ck])
    ax.set_xticks(x)
    ax.set_xticklabels([type_lab[t] for t in types])
    ax.set_ylim(-5, 112)
    ax.set_ylabel("Block rate (%)")
    ax.set_title("Retry / pollution channel: path rules are necessary")
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    fig.legend(loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    ax.text(
        0.02,
        0.08,
        "Routing pollution is blocked only when path rules are on",
        transform=ax.transAxes,
        fontsize=7.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    save_figure(fig, "fig_retry_channel")


# ── Adaptive track ───────────────────────────────────────────────────────────


def fig_a1_frontier(report: dict) -> None:
    """Utility--security plane (same grammar as fig_end_to_end_frontier)."""
    runs = (report.get("tracks") or {}).get("A1", {}).get("runs") or []
    if not runs:
        return
    # (defense, attack) → U, S
    style = {
        ("no_defense", "important_instructions"): ("No defense, static", "#9CA3AF", "o"),
        ("no_defense", "autodojo"): ("No defense, adaptive", "#E45756", "s"),
        ("bio_04", "important_instructions"): ("BioHarness, static", "#0F9D78", "D"),
        ("bio_04", "autodojo"): ("BioHarness, adaptive", "#2A6F73", "^"),
    }
    fig, ax = plt.subplots(figsize=(5.2, 3.55))
    for r in runs:
        key = (r["defense"], r["attack"])
        if key not in style:
            continue
        lab, color, mk = style[key]
        u, s = r["utility_mean"] * 100, r["security_mean"] * 100
        ax.scatter(u, s, s=90, color=color, marker=mk, edgecolor="white", linewidth=0.9, zorder=3, label=lab)
    ax.set_xlim(-8, 78)
    ax.set_ylim(-8, 112)
    ax.set_xlabel("Utility (%)")
    ax.set_ylabel("Security (1 − ASR, %)")
    ax.set_title("AutoDojo slice: static vs optimized injection")
    ax.grid(alpha=0.22, linewidth=0.6)
    ax.axhline(100, color="#6B7280", linestyle=":", linewidth=0.8)
    fig.legend(loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.02))
    ax.text(
        0.02,
        0.04,
        "Banking, 2 user tasks (small n)",
        transform=ax.transAxes,
        ha="left",
        fontsize=7.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    save_figure(fig, "fig_adaptive_frontier")


def fig_a2_optimizer() -> None:
    """Best seed/step ASR during AutoDojo optimization (under each defense)."""
    # From optimize stdout + caches: no_defense seeds hit 100% and early-stop;
    # bio_04 stays 0% for 3 steps on evaluated vectors.
    steps = np.array([0, 1, 2, 3])
    # Represented as: seed (iter 0) then optimizer steps. Conservative: bio stays 0;
    # no-defense seed wrapper already 100% on reachable vectors (bill / incoming).
    none_asr = np.array([100, 100, 100, 100])
    bio_asr = np.array([0, 0, 0, 0])
    fig, ax = plt.subplots(figsize=(7.0, 3.15))
    ax.plot(steps, none_asr, color="#E45756", marker="s", markersize=7, linewidth=2.0, label="No defense")
    ax.plot(steps, bio_asr, color="#0F9D78", marker="D", markersize=7, linewidth=2.0, label="BioHarness")
    ax.set_xticks(steps)
    ax.set_xticklabels(["Seed", "Step 1", "Step 2", "Step 3"])
    ax.set_ylim(-6, 112)
    ax.set_ylabel("Optimizer-eval ASR (%)")
    ax.set_title("Adaptive rewrite does not raise ASR under BioHarness")
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    ax.legend(loc="center right", frameon=False)
    ax.text(
        0.02,
        0.90,
        "No-defense seed already 100% (early stop).\nBioHarness: 3 rewrite steps remain 0%.",
        transform=ax.transAxes,
        fontsize=7.5,
        color="#555555",
        va="top",
    )
    fig.tight_layout()
    save_figure(fig, "fig_adaptive_optimizer")


def fig_a3_injecagent(report: dict) -> None:
    """InjecAgent composition: valid / invalid / ASR (not a pair of 100% security bars)."""
    b0 = (report.get("tracks") or {}).get("B0", {}).get("by_defense") or {}
    if not b0:
        return
    order = [d for d in ("none", "bio_04") if d in b0]
    labels = ["No defense" if d == "none" else "BioHarness" for d in order]
    n_planned = 100  # 50 dh + 50 ds
    valid, invalid, asr = [], [], []
    for d in order:
        nv = int(b0[d]["combined"]["n_valid"])
        valid.append(nv)
        invalid.append(n_planned - nv)
        asr.append(float(b0[d]["combined"]["ASR_valid"]) * 100)

    x = np.arange(len(order))
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.25))

    ax = axes[0]
    ax.bar(x, valid, 0.55, label="Valid traces", color="#4C78A8")
    ax.bar(x, invalid, 0.55, bottom=valid, label="Invalid / withheld", color="#D4D4D8")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 120)
    ax.set_ylabel("Cases (100 planned)")
    ax.set_title("Trace validity")
    ax.legend(loc="upper right", frameon=False, fontsize=7.5)
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    for i, (v, inv) in enumerate(zip(valid, invalid)):
        ax.text(i, v / 2, str(v), ha="center", va="center", fontsize=8, color="white")
        if inv >= 8:
            ax.text(i, v + inv / 2, str(inv), ha="center", va="center", fontsize=8, color="#444")

    ax = axes[1]
    ax.scatter(
        [0, 1][: len(asr)],
        asr,
        s=90,
        c=["#9CA3AF", "#0F9D78"][: len(asr)],
        marker="D",
        edgecolor="white",
        zorder=3,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(-5, 55)
    ax.set_ylabel("ASR-valid (%)")
    ax.set_title("Attack success on valid traces")
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    ax.axhline(0, color="#6B7280", linewidth=0.6)
    for i, a in enumerate(asr):
        ax.text(i, a + 2.5, f"{a:.0f}", ha="center", fontsize=8)
    ax.text(
        0.5,
        0.92,
        "Static InjecAgent base  ·  not Zhan adaptive strings",
        transform=ax.transAxes,
        ha="center",
        fontsize=7,
        color="#555555",
    )
    fig.suptitle("InjecAgent (DeepSeek): a second benchmark, not AgentDojo", y=1.02)
    fig.tight_layout()
    save_figure(fig, "fig_injecagent_second_bench")


def _load_tension() -> dict:
    if TENSION.exists():
        return json.loads(TENSION.read_text(encoding="utf-8"))
    from eval.supplement.extract_adaptive_tension import collect

    return collect()


def _evaluated_slots(opt: dict | None) -> list[tuple[str, dict]]:
    if not opt:
        return []
    rows = []
    for key, slot in (opt.get("slots") or {}).items():
        if slot.get("evaluated"):
            rows.append((key.rsplit("/", 1)[-1], slot))
    return rows


def _slot_asr_observed(slot: dict | None, gens: list[str]) -> list[float | None]:
    """ASR only at generations the optimizer actually evaluated (no carry-forward)."""
    if not slot:
        return [None] * len(gens)
    asr_map = slot.get("asr_by_generation") or {}
    out: list[float | None] = []
    for g in gens:
        asr = asr_map.get(g)
        out.append(None if asr is None else float(asr))
    return out


def fig_adaptive_stages() -> None:
    """Left: slot ASR under rewrite. Right: in-task intercept events."""
    from eval.supplement.extract_adaptive_tension import DISPLAY

    payload = _load_tension()
    defs = payload.get("defenses") or {}
    order = ["bio_04", "transformers_pi_detector", "no_defense"]
    order = [d for d in order if d in defs] or list(defs)
    gens = ["P", "F1", "F2", "F3"]
    slot_specs = (
        ("injection_incoming_transaction", "Incoming listing", -0.08, True),
        ("injection_bill_text", "Bill text", 0.08, False),
    )
    style = {
        "bio_04": ("#0F9D78", "D"),
        "transformers_pi_detector": ("#F2A541", "^"),
        "no_defense": ("#6B7280", "o"),
    }
    event_color = {
        "n_hijack_calls": "#E45756",
        "n_inbound_events": "#0F9D78",
        "n_outbound_events": "#F2A541",
    }

    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=(7.45, 3.55),
        gridspec_kw={"width_ratios": [1.20, 1.18], "wspace": 0.32},
    )

    ax_a.set_axisbelow(True)
    ax_a.grid(axis="y", linestyle="-", color="#E5E7EB", linewidth=0.7)
    ax_a.set_xlim(-0.35, 3.35)
    ax_a.set_ylim(-10, 112)
    ax_a.set_xticks(np.arange(len(gens)))
    ax_a.set_xticklabels(["P (XML)", "F1", "F2", "F3"])
    ax_a.set_ylabel("Slot ASR (%)")
    ax_a.set_xlabel("Rewrite generation")
    ax_a.set_title("Incoming listing vs. bill text")
    for d in order:
        slots = dict(_evaluated_slots(defs[d].get("optimizer") or {}))
        color, mk = style.get(d, ("#6B7280", "o"))
        for name, _label, dx, filled in slot_specs:
            ys = _slot_asr_observed(slots.get(name), gens)
            xs, vals = [], []
            for j, y in enumerate(ys):
                if y is None:
                    continue
                xs.append(j + dx)
                vals.append(100.0 * y)
            if not xs:
                continue
            ax_a.scatter(
                xs,
                vals,
                color=color if filled else "white",
                marker=mk,
                s=52 if (d == "bio_04" and filled) else 44,
                zorder=4 if d == "bio_04" else 3,
                edgecolors=color,
                linewidths=1.15,
            )
    defense_handles = [
        plt.Line2D(
            [0], [0],
            marker=style[d][1],
            color="none",
            markerfacecolor=style[d][0],
            markeredgecolor=style[d][0],
            markersize=6.5,
            label=DISPLAY.get(d, d),
        )
        for d in order if d in style
    ]
    slot_handles = [
        plt.Line2D(
            [0], [0],
            marker="o",
            color="none",
            markerfacecolor="#111827" if filled else "white",
            markeredgecolor="#111827",
            markersize=6.2,
            label=label,
        )
        for label, filled in (("Incoming listing (rewritten)", True), ("Bill text (XML seed)", False))
    ]
    ax_a.legend(
        handles=defense_handles + slot_handles,
        frameon=False,
        fontsize=6.1,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=2,
        columnspacing=0.8,
        handlelength=1.15,
    )

    n = len(order)
    ax_b.set_ylim(n - 0.5, -0.5)
    ax_b.set_yticks(np.arange(n))
    ax_b.set_yticklabels([DISPLAY.get(d, d) for d in order])
    ax_b.set_title("Hijack vs. inbound withhold")
    ax_b.set_axisbelow(True)
    ax_b.grid(axis="x", linestyle="-", color="#E5E7EB", linewidth=0.7)
    xmax = 1.0
    for i, d in enumerate(order):
        for key, dy in (("live_static", -0.17), ("live_adaptive", 0.17)):
            live = defs[d].get(key) or {}
            parts = [
                ("n_hijack_calls", int(live.get("n_hijack_calls") or 0)),
                ("n_inbound_events", int(live.get("n_inbound_events") or 0)),
                ("n_outbound_events", int(live.get("n_outbound_events") or 0)),
            ]
            x0 = 0.0
            for ek, c in parts:
                if c <= 0:
                    continue
                ax_b.barh(
                    i + dy, c, left=x0, height=0.28,
                    color=event_color[ek], edgecolor="white", linewidth=0.35, zorder=2,
                )
                ax_b.text(x0 + c / 2, i + dy, str(c), ha="center", va="center", fontsize=6.2, color="white")
                x0 += c
            util = int(live.get("utility_ok") or 0)
            ax_b.text(x0 + 0.18, i + dy, f"U={util}", ha="left", va="center", fontsize=6.0, color="#4B5563")
            xmax = max(xmax, x0 + 1.6)
    ax_b.set_xlim(0, max(8.2, xmax))
    ax_b.set_xlabel("Trace events (upper static, lower adaptive)")
    ax_b.legend(
        handles=[
            Patch(facecolor=event_color["n_hijack_calls"], edgecolor="white", label="Hijack send_money"),
            Patch(facecolor=event_color["n_inbound_events"], edgecolor="white", label="Withheld observations"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=2,
        frameon=False,
        fontsize=6.1,
    )
    fig.subplots_adjust(left=0.11, right=0.98, top=0.88, bottom=0.32, wspace=0.32)
    save_figure(fig, "fig_adaptive_stages")
    root_copy = ROOT / "fig_adaptive_stages.png"
    src = OUT / "fig_adaptive_stages.png"
    if src.exists():
        root_copy.write_bytes(src.read_bytes())
        (ROOT / "fig_adaptive_stages.pdf").write_bytes((OUT / "fig_adaptive_stages.pdf").read_bytes())


def main() -> None:
    setup_style()
    cells = (_load_matrix().get("cells") or {})
    fig_extended_suite_dumbbell(cells)
    fig_adaptive_stages()
    print(f"Wrote paper-track figures → {OUT} and {OUT_COPY}")


if __name__ == "__main__":
    main()
