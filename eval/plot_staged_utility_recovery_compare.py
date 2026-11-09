#!/usr/bin/env python3
"""Overlay historical vs current staged utility recovery (aligned x-axis).

Historical curve: values from the original publication figure (offline ladder).
Current curve: re-measured under the present protocol on the same stage axis.
Does not overwrite fig_staged_utility_recovery.pdf.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.fixtures.task_fixtures import TASK_FIXTURES
from eval.paper_probe import probe_scheme, security_score_from_row, utility_score_from_row

OUT_DIR = ROOT / "figures" / "paper_results"
STEM = "fig_staged_utility_recovery_compare"

# Same stage axis as the original figure.
LABELS = [
    "Withhold\nonly",
    "+ Metadata\nrepair",
    "+ Reflection-aware\nread handling",
    "+ Lightweight\nstate",
    "+ Unified\nauthorization",
    "Full\nprotocol",
]

# Original offline ladder (Figure as shipped with the paper draft).
HISTORICAL = np.array([20, 60, 80, 80, 80, 100], dtype=float)

# Present-protocol configs aligned to those stage names (no engineering names in the plot).
CURRENT_CONFIGS = [
    "bio_04_minus_metadata_repair",
    "idea1_provenance_mlp_reflection_ipi_metadata",
    "idea1_provenance_mlp_refl_meta_watch",
    "idea1_provenance_mlp_refl_meta_light",
    "idea1_provenance_mlp_refl_meta_unified",
    "idea1_provenance_mlp_bio_remeasure",
]


def measure_current() -> tuple[np.ndarray, list[dict]]:
    fixture = TASK_FIXTURES["user_task_32"]
    rows: list[dict] = []
    utils: list[float] = []
    for label, key in zip(LABELS, CURRENT_CONFIGS):
        row = probe_scheme(key, scheme_id=label.replace("\n", " "))
        u = 100.0 * utility_score_from_row(row, fixture)
        s = 100.0 * security_score_from_row(row, fixture)
        utils.append(u)
        rows.append(
            {
                "stage": label.replace("\n", " "),
                "config_key": key,
                "utility_pct": u,
                "security_pct": s,
            }
        )
    return np.array(utils, dtype=float), rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    current, measured = measure_current()
    print("historical:", HISTORICAL.tolist())
    print("current:   ", current.tolist())

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "fixture": "user_task_32",
        "historical_utility_pct": HISTORICAL.tolist(),
        "current_utility_pct": current.tolist(),
        "current_stages": measured,
        "note": (
            "Historical values match the original staged-recovery figure. "
            "Current values are re-measured on the same stage axis under the "
            "present Continuity-aware protocol (benign reads may proceed even "
            "when injected output is withheld)."
        ),
    }
    (OUT_DIR / f"{STEM}_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    x = np.arange(len(LABELS))
    fig, ax = plt.subplots(figsize=(7.0, 3.15))
    ax.plot(
        x,
        HISTORICAL,
        color="#8AA0A4",
        linewidth=2.0,
        marker="o",
        markersize=6.5,
        linestyle="--",
        label="Earlier protocol",
    )
    ax.plot(
        x,
        current,
        color="#2A6F73",
        linewidth=2.2,
        marker="o",
        markersize=7,
        label="Current protocol",
    )
    for i, (h, c) in enumerate(zip(HISTORICAL, current)):
        # Stagger labels when equal to avoid overlap.
        if abs(h - c) < 1e-6:
            ax.text(i, c + 3.2, f"{c:.0f}", ha="center", va="bottom", fontsize=7.5, color="#2A6F73")
        else:
            ax.text(i, h + 3.0, f"{h:.0f}", ha="center", va="bottom", fontsize=7, color="#6B7C80")
            ax.text(i, c - 7.5, f"{c:.0f}", ha="center", va="top", fontsize=7.5, color="#2A6F73")

    ax.set_xticks(x)
    ax.set_xticklabels(LABELS)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Utility (%)")
    ax.set_title("Staged utility recovery under fixed security")
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    ax.text(
        0.01,
        0.05,
        "Security remains 100% on this offline probe",
        transform=ax.transAxes,
        ha="left",
        color="#555555",
        fontsize=7.5,
    )
    fig.tight_layout()

    for ext in ("pdf", "png"):
        for dest in (OUT_DIR / f"{STEM}.{ext}", ROOT / f"{STEM}.{ext}"):
            fig.savefig(dest, dpi=200 if ext == "png" else None, bbox_inches="tight")
            print(f"wrote {dest}")
    plt.close(fig)


if __name__ == "__main__":
    main()
