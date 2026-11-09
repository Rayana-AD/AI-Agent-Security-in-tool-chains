#!/usr/bin/env python3
"""Master supplement summary figures (paper-style, DeepSeek · bio_04 v2)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "runs" / "supplement" / "figures"
PEER = ROOT / "runs" / "supplement" / "p0" / "peer_deepseek_24cond" / "report.json"
MATRIX = ROOT / "runs" / "supplement" / "p2" / "official_matrix_v2" / "matrix_summary.json"
ADAPTIVE = ROOT / "runs" / "supplement" / "p1" / "adaptive_matrix_v1" / "report.json"

# Match visualize_supplement_results.py palette
C_UTIL = "#4C72B0"
C_SEC = "#55A868"
C_ASR = "#C44E52"
C_BLOCK = "#8172B3"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def fig1_live_peer(out: Path) -> None:
    r = _load(PEER).get("stress18") or {}
    names = ["none", "spotlighting", "detector", "bio_04", "task_shield", "melon"]
    names = [n for n in names if n in r]
    labels = ["None", "Spotlight", "DeBERTa", "BioHarness", "Task Shield", "MELON"][: len(names)]
    util = [r[n]["utility"] * 100 for n in names]
    sec = [r[n]["security"] * 100 for n in names]
    x = np.arange(len(names))
    w = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, util, w, label="Utility", color=C_UTIL)
    ax.bar(x + w / 2, sec, w, label="Security (1−ASR)", color=C_SEC)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Stress-18 macro (%)")
    ax.set_title("Supplement Table 1: Live AgentDojo + peers (DeepSeek)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "supplement_fig1_live_peer.png", dpi=160)
    plt.close(fig)


def fig2_scripted_matrix(out: Path) -> None:
    m = _load(MATRIX)
    suites = m.get("suites") or []
    cfgs = ["schema_only", "idea1_only", "idea1_provenance_mlp_bio_04", "bio_04_no_hard_rules"]
    cfgs = [c for c in cfgs if c in (m.get("configs") or [])]
    cells = m.get("cells") or {}
    data = np.zeros((len(suites), len(cfgs)))
    for i, suite in enumerate(suites):
        for j, cfg in enumerate(cfgs):
            data[i, j] = ((cells.get(suite) or {}).get(cfg) or {}).get("attack_block_rate", 0) * 100
    short = [c.replace("idea1_provenance_mlp_", "bio_04").replace("idea1_", "i1_") for c in cfgs]
    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(cfgs)))
    ax.set_xticklabels(short, rotation=25, ha="right", fontsize=9)
    ax.set_yticks(range(len(suites)))
    ax.set_yticklabels(suites, fontsize=9)
    for i in range(len(suites)):
        for j in range(len(cfgs)):
            ax.text(j, i, f"{data[i, j]:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("Supplement Fig 2: Offline attack block rate (%) — 772 runs")
    fig.colorbar(im, ax=ax, label="Block rate %")
    fig.tight_layout()
    fig.savefig(out / "supplement_fig2_scripted_heatmap.png", dpi=160)
    plt.close(fig)


def fig3_retry_ablation(out: Path) -> None:
    m = _load(MATRIX)
    suite = (m.get("cells") or {}).get("retry_full") or {}
    cfgs = ["idea1_provenance_mlp_bio_04", "bio_04_no_hard_rules", "schema_only"]
    labels = ["bio_04 full", "−hard rules", "schema only"]
    types = ["retry_abuse", "state_pollution", "fragmented"]
    x = np.arange(len(types))
    w = 0.25
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for i, (cfg, lab) in enumerate(zip(cfgs, labels)):
        cell = suite.get(cfg) or {}
        by = cell.get("by_attack_type") or {}
        vals = [(by.get(t) or {}).get("block_rate", 0) * 100 for t in types]
        ax.bar(x + (i - 1) * w, vals, w, label=lab)
    ax.set_xticks(x)
    ax.set_xticklabels(types, rotation=12, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Block rate (%)")
    ax.set_title("Supplement Fig 3: Retry channel — full bio_04 vs ablation")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "supplement_fig3_retry_ablation.png", dpi=160)
    plt.close(fig)


def fig4_adaptive_live(out: Path) -> None:
    r = _load(ADAPTIVE)
    a1 = (r.get("tracks") or {}).get("A1", {}).get("runs") or []
    if not a1:
        return
    labels, asr, sec, util = [], [], [], []
    for row in a1:
        labels.append(f"{row['defense'][:4]}\n{row['attack'][:5]}")
        asr.append(row["ASR"] * 100)
        sec.append(row["security_mean"] * 100)
        util.append(row["utility_mean"] * 100)
    x = np.arange(len(labels))
    w = 0.28
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(x - w, asr, w, label="ASR", color=C_ASR)
    ax.bar(x, sec, w, label="Defense security", color=C_SEC)
    ax.bar(x + w, util, w, label="Utility", color=C_UTIL)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Banking slice (n=2 tasks, %)")
    ax.set_title("Supplement Fig 4: L3 AutoDojo — static vs optimized cache")
    ax.legend(fontsize=7, ncol=3)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "supplement_fig4_l3_autodojo.png", dpi=160)
    plt.close(fig)


def fig5_mechanism_story(out: Path) -> None:
    """Two-panel: live gain vs retry fix (bio_04 block on retry_full)."""
    peer = _load(PEER).get("stress18") or {}
    m = _load(MATRIX)
    retry_bio = ((m.get("cells") or {}).get("retry_full") or {}).get("idea1_provenance_mlp_bio_04") or {}
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    # Panel A
    ax = axes[0]
    for i, (name, lab) in enumerate([("none", "No defense"), ("bio_04", "bio_04")]):
        u, s = peer[name]["utility"] * 100, peer[name]["security"] * 100
        ax.bar(i - 0.2, u, 0.35, color=C_UTIL)
        ax.bar(i + 0.2, s, 0.35, color=C_SEC)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["No defense", "bio_04"])
    ax.set_ylim(0, 105)
    ax.set_ylabel("%")
    ax.set_title("(a) Live stress-18 U / S")
    ax.grid(axis="y", alpha=0.3)
    # Panel B
    ax = axes[1]
    types = ["retry_abuse", "state_pollution", "fragmented"]
    by = retry_bio.get("by_attack_type") or {}
    vals = [(by.get(t) or {}).get("block_rate", 0) * 100 for t in types]
    ax.bar(types, vals, color=C_BLOCK)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Block rate (%)")
    ax.set_title("(b) Offline retry_full (bio_04 v2)")
    for i, v in enumerate(vals):
        ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=9)
    fig.suptitle("Key supplement outcomes (DeepSeek · bio_04 v2)", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(out / "supplement_fig5_mechanism_summary.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig6_injecagent_b0(out: Path) -> None:
    r = _load(ADAPTIVE)
    b0 = (r.get("tracks") or {}).get("B0", {}).get("by_defense") or {}
    if not b0:
        return
    defs = list(b0.keys())
    asr = [b0[d]["combined"]["ASR_valid"] * 100 for d in defs]
    sec = [b0[d]["combined"]["security_mean"] * 100 for d in defs]
    nval = [b0[d]["combined"]["n_valid"] for d in defs]
    x = np.arange(len(defs))
    w = 0.35
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(x - w / 2, asr, w, label="ASR-valid", color=C_ASR)
    ax.bar(x + w / 2, sec, w, label="Defense security", color=C_SEC)
    ax.set_xticks(x)
    ax.set_xticklabels(defs)
    ax.set_ylim(0, 105)
    ax.set_ylabel("%")
    ax.set_title(f"Supplement Fig 6: InjecAgent B0 (n_valid={nval})")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "supplement_fig6_injecagent_b0.png", dpi=160)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig1_live_peer(FIG)
    fig2_scripted_matrix(FIG)
    fig3_retry_ablation(FIG)
    fig4_adaptive_live(FIG)
    fig5_mechanism_story(FIG)
    fig6_injecagent_b0(FIG)
    print(f"Wrote supplement_fig1–6 → {FIG}")


if __name__ == "__main__":
    main()
