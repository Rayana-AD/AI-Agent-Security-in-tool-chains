"""Ordered storage layout for P0–P2 supplement experiments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPPLEMENT_ROOT = ROOT / "runs" / "supplement"


class SupplementRunStore:
    """Write results under runs/supplement/<phase>/<experiment_id>/.

    Layout:
        runs/supplement/
          manifest.json                 # master index (append-only entries)
          p0/peer_deepseek_24cond/
            report.json
            table.md
          p1/adaptive_protocol_v1/
            protocol.json
            smoke/report.json
          p2/path_smuggle_v1/
            report.json
            records.csv
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or DEFAULT_SUPPLEMENT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def experiment_dir(self, phase: str, experiment_id: str) -> Path:
        path = self.root / phase / experiment_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, phase: str, experiment_id: str, name: str, payload: Any) -> Path:
        out = self.experiment_dir(phase, experiment_id) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._register(phase, experiment_id, str(out.relative_to(self.root)))
        return out

    def write_text(self, phase: str, experiment_id: str, name: str, text: str) -> Path:
        out = self.experiment_dir(phase, experiment_id) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        self._register(phase, experiment_id, str(out.relative_to(self.root)))
        return out

    def _register(self, phase: str, experiment_id: str, artifact: str) -> None:
        manifest: dict[str, Any]
        if self.manifest_path.exists():
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"version": 1, "entries": []}
        manifest["entries"].append(
            {
                "phase": phase,
                "experiment_id": experiment_id,
                "artifact": artifact,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
