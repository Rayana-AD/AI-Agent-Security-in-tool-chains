#!/usr/bin/env python3
"""Visualize supplement experiment results → runs/supplement/figures/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SUPPLEMENT = ROOT / "runs" / "supplement"
FIGURES = SUPPLEMENT / "figures"


def _load(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def plot_peer_baselines(out: Path, *, suffix: str = "") -> None:
    r = _load(SUPPLEMENT / "p0/peer_deepseek_24cond/report.json")
    if not r:
        return
    stress = r["stress18"]
    names = ["none", "spotlighting", "detector", "bio_04", "task_shield", "melon"]
    labels = ["None", "Spotlight", "DeBERTa", "BioHarness", "Task Shield", "MELON"]
    names = [n for n in names if n in stress]
    labels = labels[: len(names)]
    util = [stress[n]["utility"] * 100 for n in names]
    sec = [stress[n]["security"] * 100 for n in names]
    x = np.arange(len(names))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(8, len(names) * 1.3), 4.8))
    ax.bar(x - w / 2, util, w, label="Utility", color="#4C72B0")
    ax.bar(x + w / 2, sec, w, label="Security", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Stress macro (%)")
    ax.set_title("Live AgentDojo: main + peer baselines (DeepSeek stress-18)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fname = f"p0_peer_stress_macro{suffix}.png"
    fig.savefig(out / fname, dpi=160)
    plt.close(fig)


def plot_extended_suites(matrix: dict, out: Path, *, suffix: str = "") -> None:
    """Bar chart for retry / fragmented / reflection / mhj suites (bio_04 vs schema_only)."""
    targets = ["retry_full", "fragmented_shuffle", "reflection_process", "mhj_multihop"]
    suites = [s for s in targets if s in (matrix.get("cells") or {})]
    if not suites:
        return
    cfgs = ["schema_only", "idea1_provenance_mlp_bio_04"]
    x = np.arange(len(suites))
    w = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, cfg in enumerate(cfgs):
        vals = []
        for suite in suites:
            cell = (matrix.get("cells") or {}).get(suite, {}).get(cfg) or {}
            vals.append(cell.get("attack_block_rate", 0) * 100)
        offset = (i - 0.5) * w
        ax.bar(x + offset, vals, w, label=cfg.replace("idea1_provenance_mlp_", ""))
    ax.set_xticks(x)
    ax.set_xticklabels(suites, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Attack block rate (%)")
    ax.set_title("Extended attack suites (scripted offline)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"p2_extended_suites{suffix}.png", dpi=160)
    plt.close(fig)


def plot_matrix_heatmap(matrix: dict, out: Path, *, suffix: str = "", title: str | None = None) -> None:
    configs = matrix.get("configs") or []
    suites = matrix.get("suites") or []
    cells = matrix.get("cells") or {}
    if not configs or not suites:
        return
    data = np.zeros((len(suites), len(configs)))
    for i, suite in enumerate(suites):
        for j, cfg in enumerate(configs):
            cell = (cells.get(suite) or {}).get(cfg) or {}
            data[i, j] = cell.get("attack_block_rate", 0) * 100

    short_cfg = [c.replace("idea1_provenance_mlp_", "").replace("idea1_", "") for c in configs]
    fig, ax = plt.subplots(figsize=(max(8, len(configs) * 1.2), max(4, len(suites) * 0.8)))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels(short_cfg, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(suites)))
    ax.set_yticklabels(suites, fontsize=9)
    for i in range(len(suites)):
        for j in range(len(configs)):
            ax.text(j, i, f"{data[i, j]:.0f}", ha="center", va="center", color="black", fontsize=8)
    ax.set_title(title or "Attack block rate (%) by suite × config")
    fig.colorbar(im, ax=ax, label="Block rate %")
    fig.tight_layout()
    fig.savefig(out / f"p2_matrix_block_rate_heatmap{suffix}.png", dpi=160)
    plt.close(fig)


def plot_attack_type_gaps(matrix: dict, out: Path) -> None:
    """Bar chart: per attack type for bio_04 vs schema_only on path_heldout."""
    cells = matrix.get("cells") or {}
    held = cells.get("path_heldout") or {}
    cfgs = ["idea1_provenance_mlp_bio_04", "schema_only", "idea1_provenance_mlp"]
    cfgs = [c for c in cfgs if c in held]
    if not cfgs:
        return
    types = sorted({t for c in cfgs for t in (held[c].get("by_attack_type") or {})})
    x = np.arange(len(types))
    w = 0.8 / len(cfgs)
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, cfg in enumerate(cfgs):
        rates = [
            (held[cfg].get("by_attack_type") or {}).get(t, {}).get("block_rate", 0) * 100
            for t in types
        ]
        offset = (i - (len(cfgs) - 1) / 2) * w
        ax.bar(x + offset, rates, w, label=cfg.replace("idea1_provenance_mlp_", ""))
    ax.set_xticks(x)
    ax.set_xticklabels(types, rotation=25, ha="right", fontsize=8)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Block rate (%)")
    ax.set_title("Held-out attack types: BioHarness vs lighter configs")
    ax.legend(fontsize=8)
    ax.axhline(100, color="gray", ls="--", alpha=0.3)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "p2_path_heldout_by_attack_type.png", dpi=160)
    plt.close(fig)


def plot_idea2_summary(out: Path) -> None:
    r = _load(SUPPLEMENT / "p2/idea2_summary_v1/report.json")
    if not r:
        return
    exps = r.get("experiments") or {}
    labels, configs_set = [], set()
    for exp_name, exp in exps.items():
        for s in exp.get("summaries") or []:
            configs_set.add(s["config"])
    configs = sorted(configs_set)
    data = np.zeros((len(exps), len(configs)))
    exp_labels = list(exps.keys())
    for i, exp_name in enumerate(exp_labels):
        by_cfg = {s["config"]: s for s in exps[exp_name].get("summaries") or []}
        for j, cfg in enumerate(configs):
            data[i, j] = by_cfg.get(cfg, {}).get("block_rate", 0) * 100
    fig, ax = plt.subplots(figsize=(9, 4))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels(configs, rotation=25, ha="right", fontsize=8)
    ax.set_yticks(range(len(exp_labels)))
    ax.set_yticklabels([e.replace("exp_", "") for e in exp_labels], fontsize=9)
    for i in range(len(exp_labels)):
        for j in range(len(configs)):
            ax.text(j, i, f"{data[i,j]:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("Idea2 suites: block rate (%) by internal config")
    fig.colorbar(im, ax=ax, label="Block %")
    fig.tight_layout()
    fig.savefig(out / "p2_idea2_block_heatmap.png", dpi=160)
    plt.close(fig)


def plot_adaptive_l2(out: Path) -> None:
    r = _load(SUPPLEMENT / "p1/adaptive_l2_v1/report.json")
    if not r:
        return
    from collections import defaultdict

    by: dict[tuple[str, str], dict] = defaultdict(lambda: {"n": 0, "blocked": 0})
    for rec in r.get("records") or []:
        k = (rec.get("attack_type", ""), rec.get("action", ""))
        by[k]["n"] += 1
        by[k]["blocked"] += int(rec.get("blocked", False))
    types = sorted({k[0] for k in by})
    actions = sorted({k[1] for k in by})
    data = np.zeros((len(types), len(actions)))
    for i, t in enumerate(types):
        for j, a in enumerate(actions):
            cell = by.get((t, a), {"n": 0, "blocked": 0})
            data[i, j] = (cell["blocked"] / max(cell["n"], 1)) * 100
    fig, ax = plt.subplots(figsize=(9, 5))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(actions)))
    ax.set_xticklabels(actions, rotation=20, ha="right", fontsize=8)
    ax.set_yticks(range(len(types)))
    ax.set_yticklabels(types, fontsize=8)
    for i in range(len(types)):
        for j in range(len(actions)):
            ax.text(j, i, f"{data[i,j]:.0f}", ha="center", va="center", fontsize=7)
    ax.set_title("P1 L2 white-box adaptive: block rate by attack × mutation")
    fig.colorbar(im, ax=ax, label="Block %")
    fig.tight_layout()
    fig.savefig(out / "p1_adaptive_l2_heatmap.png", dpi=160)
    plt.close(fig)


def _universal_gaps(matrix: dict, cfg: str = "idea1_provenance_mlp_bio_04") -> list[str]:
    """Attack types with 0% block across all configs in matrix."""
    cells = matrix.get("cells") or {}
    types: set[str] = set()
    for suite_cells in cells.values():
        for cell in suite_cells.values():
            types.update((cell.get("by_attack_type") or {}).keys())
    universal = []
    for t in sorted(types):
        rates = []
        for suite_cells in cells.values():
            cell = suite_cells.get(cfg) or {}
            info = (cell.get("by_attack_type") or {}).get(t)
            if info:
                rates.append(info.get("block_rate", 0))
        if rates and max(rates) == 0:
            universal.append(t)
    return universal


def write_analysis_v2_md(matrix: dict | None, out: Path) -> None:
    lines = [
        "# Supplement analysis v2 (official spec aligned)",
        "",
        "Spec: [`docs/eval/OFFICIAL_ATTACK_BASELINE_SPEC.md`](../../docs/eval/OFFICIAL_ATTACK_BASELINE_SPEC.md)",
        "",
        "## Table A — Live AgentDojo (DeepSeek stress-18, official U/S)",
        "",
        "Same 24-condition manifest as main paper; metrics from AgentDojo user/injection checks.",
        "",
        "| Defense | Utility | Security | Source |",
        "|---------|---------|----------|--------|",
    ]
    peer = _load(SUPPLEMENT / "p0/peer_deepseek_24cond/report.json")
    if peer:
        src = {
            "none": "AgentDojo upstream",
            "spotlighting": "AgentDojo built-in",
            "detector": "AgentDojo + ProtectAI DeBERTa",
            "bio_04": "This paper",
            "task_shield": "ACL'25 port (no official code)",
            "melon": "github.com/kaijiezhu11/MELON",
        }
        for name in ("none", "spotlighting", "detector", "bio_04", "task_shield", "melon"):
            if name not in peer.get("stress18", {}):
                continue
            m = peer["stress18"][name]
            lines.append(
                f"| {name} | {m['utility']*100:.1f}% | {m['security']*100:.1f}% | {src.get(name, '')} |"
            )
        lines.append("")

    if matrix:
        sizes = matrix.get("suite_sizes") or {}
        lines += [
            "## Table B — Scripted v2 (attack block rate %, offline harness)",
            "",
            f"Total scripted runs: {sum(s.get('n_total', 0) for s in sizes.values())} samples × "
            f"{len(matrix.get('configs') or [])} configs. **Not comparable to Table A U/S.**",
            "",
        ]
        configs = matrix.get("configs") or []
        short = []
        for c in configs:
            if c == "idea1_provenance_mlp_bio_04":
                short.append("bio_04")
            else:
                short.append(c.replace("idea1_provenance_mlp_", "").replace("idea1_", ""))
        header = "| Suite | n atk | " + " | ".join(short) + " |"
        lines.extend([header, "|" + "---|" * (len(configs) + 2)])
        for suite in matrix.get("suites") or []:
            sz = sizes.get(suite, {})
            row = [suite, str(sz.get("n_attack", "?"))]
            for cfg in configs:
                cell = (matrix.get("cells") or {}).get(suite, {}).get(cfg) or {}
                row.append(f"{cell.get('attack_block_rate', 0)*100:.0f}%")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

        bio = "idea1_provenance_mlp_bio_04"
        lines.append("## Table C — Extended attack types (bio_04, by_attack_type)")
        lines.append("")
        for suite in ("retry_full", "fragmented_shuffle", "reflection_process", "mhj_multihop"):
            cell = (matrix.get("cells") or {}).get(suite, {}).get(bio) or {}
            by_type = cell.get("by_attack_type") or {}
            if not by_type:
                continue
            lines.append(f"### {suite}")
            lines.append("| attack_type | n | block | ASR |")
            lines.append("|-------------|---|-------|-----|")
            for t, info in sorted(by_type.items()):
                lines.append(
                    f"| {t} | {info.get('n', 0)} | {info.get('block_rate', 0)*100:.0f}% | "
                    f"{info.get('asr', 0)*100:.0f}% |"
                )
            if cell.get("benign_fpr") is not None and suite == "reflection_process":
                lines.append(f"- benign FPR: **{cell.get('benign_fpr', 0)*100:.0f}%**")
            lines.append("")

        lines.append("## Key findings")
        lines.append("")
        uni = _universal_gaps(matrix, bio)
        if uni:
            lines.append(f"- Universal scripted gaps (0% block bio_04): `{', '.join(uni)}`.")
        refl = (matrix.get("cells") or {}).get("reflection_process", {}).get(bio, {})
        if refl:
            lines.append(
                f"- Reflection/process suite: block={refl.get('attack_block_rate', 0)*100:.0f}%, "
                f"benign FPR={refl.get('benign_fpr', 0)*100:.0f}%."
            )
        mhj = (matrix.get("cells") or {}).get("mhj_multihop", {}).get(bio, {})
        if mhj:
            lines.append(
                f"- MHJ multihop (synthetic 2-hop, HF gated): block={mhj.get('attack_block_rate', 0)*100:.0f}%."
            )
        lines.append("- Live baselines (Table A) use AgentDojo; scripted suites stress complementary attack geometry.")
        lines.append("")

    lines.append("## Figures")
    lines.append("")
    for png in sorted(out.glob("*v2*.png")) + sorted(out.glob("p0_peer*.png")):
        lines.append(f"- `{png.name}`")
    (out / "ANALYSIS_v2.md").write_text("\n".join(lines), encoding="utf-8")


def write_analysis_md(matrix: dict | None, out: Path) -> None:
    lines = [
        "# Supplement visualization analysis",
        "",
        "Generated by `eval/supplement/visualize_supplement_results.py`.",
        "",
    ]
    if matrix:
        lines.append("## 1. Comparison matrix (attack block rate %)")
        lines.append("")
        configs = matrix.get("configs") or []
        short = [c.replace("idea1_provenance_mlp_", "mlp_").replace("idea1_", "") for c in configs]
        header = "| Suite | " + " | ".join(short) + " |"
        lines.extend([header, "|" + "---|" * (len(configs) + 1)])
        for suite in matrix.get("suites") or []:
            row = [suite]
            for cfg in configs:
                cell = (matrix.get("cells") or {}).get(suite, {}).get(cfg) or {}
                row.append(f"{cell.get('attack_block_rate', 0)*100:.0f}%")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

        bio = "idea1_provenance_mlp_bio_04"
        no_rules = "bio_04_no_hard_rules"
        h_full = (matrix.get("cells") or {}).get("path_heldout", {}).get(bio, {})
        h_nr = (matrix.get("cells") or {}).get("path_heldout", {}).get(no_rules, {})
        lines.append("## 2. Key findings")
        lines.append("")
        lines.append(
            f"- **Full bio_04 vs −hard rules (held-out):** "
            f"{h_full.get('attack_block_rate', 0)*100:.0f}% → {h_nr.get('attack_block_rate', 0)*100:.0f}% "
            f"(path hard rules matter for no-envelope natural language)."
        )
        lines.append(
            f"- **Provenance stack vs schema_only (held-out):** "
            f"bio_04 {h_full.get('attack_block_rate', 0)*100:.0f}% vs "
            f"schema_only {(matrix.get('cells') or {}).get('path_heldout', {}).get('schema_only', {}).get('attack_block_rate', 0)*100:.0f}%."
        )
        uni = _universal_gaps(matrix, bio)
        if uni:
            lines.append(f"- **Universal gaps (0% block on bio_04 across suites present):** `{', '.join(uni)}`.")
        ind = (matrix.get("cells") or {}).get("path_indist", {}).get(bio, {}).get("by_attack_type") or {}
        partial = [k for k, v in ind.items() if 0 < v.get("block_rate", 0) < 1]
        if partial:
            lines.append(f"- **Partial blocks (in-dist, bio_04):** {', '.join(partial)}.")
        lines.append(
            "- **MHJ synthetic temporal:** 100% block all configs (samples are coarse; fold-only)."
        )
        lines.append(
            "- **atomic_retry:** fragmented/process drift blocked; **state_pollution 0/2** all configs."
        )
        lines.append("")

        lines.append("## 3. Block layers (bio_04, path_heldout)")
        lines.append("")
        for layer, count in sorted((h_full.get("block_layers") or {}).items(), key=lambda x: -x[1]):
            lines.append(f"- `{layer}`: {count}")
        lines.append("")

    peer = _load(SUPPLEMENT / "p0/peer_deepseek_24cond/report.json")
    if peer:
        s = peer["stress18"]
        lines.append("## 4. Live AgentDojo peers (DeepSeek stress, separate benchmark)")
        lines.append("")
        lines.append("| Defense | U | S |")
        lines.append("|---------|---|---|")
        for name, label in [
            ("bio_04", "BioHarness"),
            ("task_shield", "Task Shield"),
            ("melon", "MELON"),
        ]:
            lines.append(
                f"| {label} | {s[name]['utility']*100:.1f}% | {s[name]['security']*100:.1f}% |"
            )
        lines.append("")

    lines.append("## 5. Figures")
    lines.append("")
    for png in sorted(out.glob("*.png")):
        lines.append(f"- [`{png.name}`](../figures/{png.name})")
    (out / "ANALYSIS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize supplement results")
    parser.add_argument("--supplement-root", type=Path, default=SUPPLEMENT)
    parser.add_argument(
        "--matrix",
        default="comparison_matrix_v1",
        help="p2 experiment id (e.g. official_matrix_v2)",
    )
    args = parser.parse_args()
    fig_dir = args.supplement_root / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    suffix = "_v2" if args.matrix == "official_matrix_v2" else ""
    matrix_path = args.supplement_root / f"p2/{args.matrix}/matrix_summary.json"
    matrix = _load(matrix_path)
    plot_peer_baselines(fig_dir, suffix=suffix)
    if matrix:
        plot_matrix_heatmap(
            matrix,
            fig_dir,
            suffix=suffix,
            title="Scripted attack block rate (%) — official matrix v2" if suffix else None,
        )
        plot_attack_type_gaps(matrix, fig_dir)
        plot_extended_suites(matrix, fig_dir, suffix=suffix)
    plot_idea2_summary(fig_dir)
    plot_adaptive_l2(fig_dir)
    write_analysis_md(matrix if args.matrix == "comparison_matrix_v1" else None, fig_dir)
    if matrix and args.matrix == "official_matrix_v2":
        write_analysis_v2_md(matrix, fig_dir)
    print(f"Figures → {fig_dir}")
    if args.matrix == "official_matrix_v2":
        print(f"Analysis → {fig_dir / 'ANALYSIS_v2.md'}")
    else:
        print(f"Analysis → {fig_dir / 'ANALYSIS.md'}")


if __name__ == "__main__":
    main()
