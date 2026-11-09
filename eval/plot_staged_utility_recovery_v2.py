#!/usr/bin/env python3
"""Re-measure controlled repair ladder under current bio_04 configs; write a new figure.

Does not overwrite fig_staged_utility_recovery.pdf (legacy hardcoded 20/60/80/100).
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

# Paper-facing ladder: increasingly complete bio_04-family configs (measured, not hardcoded).
STAGES: list[tuple[str, str, str]] = [
    (
        "Withhold\nonly",
        "bio_04_minus_metadata_repair",
        "No metadata repair (withhold IPI output)",
    ),
    (
        "+ Metadata\nrepair",
        "bio_04_minus_reflection",
        "Metadata strip on; Reflective Fold off",
    ),
    (
        "Full\nprotocol",
        "idea1_provenance_mlp_bio_04",
        "Current BioHarness default (bio_04)",
    ),
]

# Extra diagnostics (not all plotted on the main curve).
EXTRA: list[tuple[str, str]] = [
    ("minus_continuity", "bio_04_minus_goal_continuity"),
    ("minus_feature_shuffle", "bio_04_minus_feature_shuffle"),
    ("minus_hard_rules", "bio_04_minus_hard_rules"),
    ("legacy_meta_full", "idea1_provenance_mlp_refl_meta_full"),
]

OUT_DIR = ROOT / "figures" / "paper_results"
STEM = "fig_staged_utility_recovery_v2"


def _run(config_key: str, scheme_id: str) -> dict:
    fixture = TASK_FIXTURES["user_task_32"]
    row = probe_scheme(config_key, scheme_id=scheme_id)
    u = utility_score_from_row(row, fixture)
    s = security_score_from_row(row, fixture)
    return {
        "scheme_id": scheme_id,
        "config_key": config_key,
        "utility_pct": round(100.0 * u, 1),
        "security_pct": round(100.0 * s, 1),
        "output_withheld": bool(row["output_withheld"]),
        "id7_visible": bool(row["id7_visible"]),
        "get_file_by_id_allowed": bool(row.get("get_file_by_id_allowed")),
        "create_file_allowed": bool(row.get("create_file_allowed")),
        "share_file_allowed": bool(row.get("share_file_allowed")),
        "send_email_allowed": bool(row.get("send_email_allowed")),
        "utility_keys": list(fixture.utility_keys),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stage_rows = []
    for label, key, note in STAGES:
        row = _run(key, label.replace("\n", " "))
        row["plot_label"] = label
        row["note"] = note
        stage_rows.append(row)
        print(f"[stage] {label!r:30s} U={row['utility_pct']} S={row['security_pct']} ({key})")

    extra_rows = []
    for sid, key in EXTRA:
        row = _run(key, sid)
        extra_rows.append(row)
        print(f"[extra] {sid:28s} U={row['utility_pct']} S={row['security_pct']} ({key})")

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "fixture": "user_task_32",
        "note": (
            "Measured under current bio_04-family configs. "
            "Legacy fig_staged_utility_recovery.pdf used a hardcoded 20/60/80/100 ladder "
            "and older meta_full scheme names; this v2 does not overwrite it. "
            "On this fixture, minus_continuity matches full (100), so Continuity is not "
            "binding here—unlike the historical −20 ΔU claim on the old probe."
        ),
        "stages": stage_rows,
        "diagnostics": extra_rows,
    }
    report_path = OUT_DIR / f"{STEM}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {report_path}")

    labels = [r["plot_label"] for r in stage_rows]
    utility = np.array([r["utility_pct"] for r in stage_rows], dtype=float)
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(6.2, 3.1))
    ax.plot(x, utility, color="#2A6F73", linewidth=2.2, marker="o", markersize=7)
    for i, value in enumerate(utility):
        ax.text(i, value + 3.2, f"{value:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Utility (%)")
    ax.set_title("Staged utility recovery (re-measured, bio_04 probe)")
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.text(
        0.99,
        0.05,
        "Security 100% on this offline probe · current configs",
        transform=ax.transAxes,
        ha="right",
        color="#555555",
        fontsize=7.5,
    )
    fig.tight_layout()

    for ext in ("pdf", "png"):
        path = OUT_DIR / f"{STEM}.{ext}"
        fig.savefig(path, dpi=200 if ext == "png" else None, bbox_inches="tight")
        # Mirror next to legacy root copies without touching the original stem.
        root_path = ROOT / f"{STEM}.{ext}"
        fig.savefig(root_path, dpi=200 if ext == "png" else None, bbox_inches="tight")
        print(f"wrote {path}")
        print(f"wrote {root_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
