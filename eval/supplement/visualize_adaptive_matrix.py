#!/usr/bin/env python3
"""Paper-style figures for P1 adaptive_matrix_v1 (+ track D retry)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "runs" / "supplement" / "p1" / "adaptive_matrix_v1" / "report.json"
FIG = ROOT / "runs" / "supplement" / "figures"


def _load() -> dict:
    if not REPORT.is_file():
        return {}
    return json.loads(REPORT.read_text(encoding="utf-8"))


def plot_live_static_vs_bio(report: dict, out: Path) -> None:
    a0 = (report.get("tracks") or {}).get("A0", {}).get("metrics") or {}
    if "none" not in a0 or "bio_04" not in a0:
        return
    names = ["none", "bio_04"]
    labels = ["No defense", "BioHarness bio_04"]
    util = [a0[n]["utility"] * 100 for n in names]
    sec = [a0[n]["security_mean"] * 100 for n in names]
    x = np.arange(2)
    w = 0.35
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.bar(x - w / 2, util, w, label="Utility", color="#4C72B0")
    ax.bar(x + w / 2, sec, w, label="Security (1−ASR)", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Stress-18 macro (%)")
    ax.set_title("Track A0: AgentDojo static (DeepSeek)")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "p1_adaptive_A0_static.png", dpi=160)
    plt.close(fig)


def plot_autodojo_slice(report: dict, out: Path) -> None:
    runs = (report.get("tracks") or {}).get("A1", {}).get("runs") or []
    if not runs:
        return
    labels, asr, sec = [], [], []
    for r in runs:
        labels.append(f"{r['defense'][:4]}\n{r['attack'][:6]}")
        asr.append(r["ASR"] * 100)
        sec.append(r["security_mean"] * 100)
    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.1), 4.2))
    ax.bar(x - w / 2, asr, w, label="ASR (attack success)", color="#C44E52")
    ax.bar(x + w / 2, sec, w, label="Defense security", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Banking slice (2 tasks, %)")
    ax.set_title("Track A1: Static vs AutoDojo cache")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "p1_adaptive_A1_autodojo.png", dpi=160)
    plt.close(fig)


def plot_injecagent(report: dict, out: Path) -> None:
    b0 = (report.get("tracks") or {}).get("B0", {}).get("by_defense") or {}
    if not b0:
        return
    defs = list(b0.keys())
    labels = ["none" if d == "none" else d for d in defs]
    asr = [b0[d]["combined"]["ASR_valid"] * 100 for d in defs]
    sec = [b0[d]["combined"]["security_mean"] * 100 for d in defs]
    x = np.arange(len(defs))
    w = 0.35
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(x - w / 2, asr, w, label="ASR-valid", color="#C44E52")
    ax.bar(x + w / 2, sec, w, label="Defense security", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 105)
    ax.set_ylabel(f"InjecAgent base (n≈{b0[defs[0]]['combined']['n_valid']*2//len(defs)} per arm)")
    ax.set_title("Track B0: InjecAgent static (DeepSeek)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "p1_adaptive_B0_injecagent.png", dpi=160)
    plt.close(fig)


def plot_retry_track_d(report: dict, out: Path) -> None:
    suite_map = (report.get("tracks") or {}).get("D", {}).get("suites") or {}
    focus = ["retry_full", "path_indist", "fragmented_shuffle"]
    names = [s for s in focus if s in suite_map]
    if not names:
        return
    vals = [suite_map[s]["attack_block_rate"] * 100 for s in names]
    fig, ax = plt.subplots(figsize=(6, 3.8))
    ax.bar(names, vals, color="#8172B3")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Attack block rate (%)")
    ax.set_title("Track D: L2 scripted (bio_04 v2 offline)")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(vals):
        ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "p1_adaptive_D_retry_scripted.png", dpi=160)
    plt.close(fig)


def write_analysis_md(report: dict, out: Path) -> None:
    lines = [
        "# P1 Adaptive matrix (DeepSeek · bio_04 v2)\n",
        f"Generated from `{REPORT.relative_to(ROOT)}`.\n",
        "## Reading guide\n",
        "- **Live Security** = 1 − ASR (higher is safer).\n",
        "- **Track D block rate** = offline harness; complements live, does not replace it.\n",
        "- **Retry** tests gate/retry side channel; **AutoDojo** tests LLM-optimized injection text.\n",
    ]
    a0 = (report.get("tracks") or {}).get("A0", {}).get("metrics") or {}
    if a0.get("bio_04"):
        lines.append(
            f"\n## A0 stress-18\n- none: U={a0['none']['utility']*100:.1f}% S={a0['none']['security_mean']*100:.1f}%\n"
            f"- bio_04: U={a0['bio_04']['utility']*100:.1f}% S={a0['bio_04']['security_mean']*100:.1f}%\n"
        )
    b0 = (report.get("tracks") or {}).get("B0", {}).get("by_defense") or {}
    if b0:
        lines.append("## B0 InjecAgent\n")
        for d, m in b0.items():
            c = m["combined"]
            lines.append(
                f"- {d}: ASR-valid={c['ASR_valid']*100:.1f}% → defense security={c['security_mean']*100:.1f}% (n_valid={c['n_valid']})\n"
            )
    (out / "ANALYSIS_adaptive_matrix.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    report = _load()
    if not report:
        print("No report; run run_p1_adaptive_matrix_v1.py first")
        return
    plot_live_static_vs_bio(report, FIG)
    plot_autodojo_slice(report, FIG)
    plot_injecagent(report, FIG)
    plot_retry_track_d(report, FIG)
    write_analysis_md(report, FIG)
    print(f"Figures → {FIG}/p1_adaptive_*.png")


if __name__ == "__main__":
    main()
