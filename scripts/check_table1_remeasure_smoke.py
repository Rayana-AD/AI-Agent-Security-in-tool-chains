#!/usr/bin/env python3
"""Table 1 remeasure smoke gate (wrapper; defense=bio_remeasure)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Delegate to shared checker with Table 1 defense label.
if __name__ == "__main__":
    sys.argv[0] = str(ROOT / "scripts" / "check_bio05_remeasure_smoke.py")
    if "--defense" not in sys.argv:
        sys.argv.extend(["--defense", "bio_remeasure"])
    runpy.run_path(str(ROOT / "scripts" / "check_bio05_remeasure_smoke.py"), run_name="__main__")
