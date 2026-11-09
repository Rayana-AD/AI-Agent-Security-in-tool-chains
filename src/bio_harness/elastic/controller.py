"""Elastic gating: increase shuffle rounds on probing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ElasticController:
    default_rounds: int = 2
    max_rounds: int = 5
    enabled: bool = True

    def shuffle_rounds(self, probe_count: int) -> int:
        if not self.enabled:
            return self.default_rounds
        if probe_count < 2:
            return self.default_rounds
        if probe_count < 4:
            return min(self.default_rounds + 1, self.max_rounds)
        return self.max_rounds

    def gate_strict(self, probe_count: int) -> bool:
        return self.enabled and probe_count >= 4
