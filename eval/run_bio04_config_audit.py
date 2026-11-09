#!/usr/bin/env python3
"""Print bio_04 reviewer ablation config alignment (continuity profiles)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.bio04_reviewer_ablations import audit_alignment


def main() -> None:
    report = audit_alignment()
    print(json.dumps(report, indent=2))
    if not report["aligned"]:
        print("\nAlignment issues:", file=sys.stderr)
        for note in report["notes"]:
            print(f"  - {note}", file=sys.stderr)
        raise SystemExit(1)
    print("\nAll reviewer ablation configs aligned with bio_04.", flush=True)


if __name__ == "__main__":
    main()
