"""Persistent cache for Crossref/arXiv metadata lookups."""

from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "citation_verify"


class CitationCache:
    def __init__(self, cache_dir: Path | None = None, ttl_seconds: float = 86400 * 7) -> None:
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if time.time() - data.get("_cached_at", 0) > self.ttl_seconds:
            return None
        return data.get("payload")

    def set(self, namespace: str, key: str, payload: dict[str, Any]) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"_cached_at": time.time(), "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
