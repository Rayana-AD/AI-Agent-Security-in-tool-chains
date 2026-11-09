"""Raw vs Trusted state partition with write barriers."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


class StateWriteError(PermissionError):
    """Raised when an untrusted write to TrustedState is attempted."""


@dataclass
class RawState:
    turn_history: list[dict[str, Any]] = field(default_factory=list)
    probe_count: int = 0
    failed_attempts: list[dict[str, Any]] = field(default_factory=list)
    session_id: str = ""
    started_at: float = 0.0

    def append_turn(self, node: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.turn_history.append(
            {"node": node, "content": content, "metadata": metadata or {}}
        )


@dataclass
class TrustedState:
    approved_facts: list[str] = field(default_factory=list)
    approved_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    approved_plans: list[str] = field(default_factory=list)

    def append_fact(self, fact: str, *, authorized: bool = True) -> None:
        if not authorized:
            raise StateWriteError("Unauthorized write to TrustedState.approved_facts")
        if fact and fact not in self.approved_facts:
            self.approved_facts.append(fact)

    def append_tool_call(self, call: dict[str, Any], *, authorized: bool = True) -> None:
        if not authorized:
            raise StateWriteError("Unauthorized write to TrustedState.approved_tool_calls")
        self.approved_tool_calls.append(copy.deepcopy(call))

    def append_plan(self, plan: str, *, authorized: bool = True) -> None:
        if not authorized:
            raise StateWriteError("Unauthorized write to TrustedState.approved_plans")
        if plan:
            self.approved_plans.append(plan)


@dataclass
class PartitionedState:
    raw: RawState = field(default_factory=RawState)
    trusted: TrustedState = field(default_factory=TrustedState)
    untrusted_external: list[str] = field(default_factory=list)
    use_partition: bool = True

    def write_trusted(
        self,
        *,
        facts: list[str] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        plans: list[str] | None = None,
        authorized: bool = True,
    ) -> None:
        if self.use_partition and not authorized:
            raise StateWriteError("Partitioned write requires authorization after gate+cleave")
        for f in facts or []:
            self.trusted.append_fact(f, authorized=authorized or not self.use_partition)
        for tc in tool_calls or []:
            self.trusted.append_tool_call(tc, authorized=authorized or not self.use_partition)
        for p in plans or []:
            self.trusted.append_plan(p, authorized=authorized or not self.use_partition)

    def snapshot_trusted(self) -> dict[str, Any]:
        return {
            "approved_facts": list(self.trusted.approved_facts),
            "approved_tool_calls": copy.deepcopy(self.trusted.approved_tool_calls),
            "approved_plans": list(self.trusted.approved_plans),
        }

    def snapshot_for_gate(self) -> dict[str, Any]:
        snap = self.snapshot_trusted()
        snap["_global_pollution"] = getattr(self, "_global", {})
        return snap

    def merge_global_pollution(self, key: str, value: Any) -> None:
        """Simulate global-state pollution (ablation / attack path)."""
        if not hasattr(self, "_global"):
            self._global = {}
        self._global[key] = value

    def read_global(self, key: str, default: Any = None) -> Any:
        g = getattr(self, "_global", {})
        return g.get(key, default)
