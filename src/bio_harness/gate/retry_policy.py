"""Retry policy for limited backflow."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_retries: int = 3
    session_ttl_seconds: float = 600.0

    def can_retry(self, retry_count: int, started_at: float) -> tuple[bool, str]:
        if retry_count >= self.max_retries:
            return False, "max_retries_exceeded"
        if started_at and (time.time() - started_at) > self.session_ttl_seconds:
            return False, "session_ttl_exceeded"
        return True, ""

    def record_probe(self, probe_count: int) -> int:
        return probe_count + 1
