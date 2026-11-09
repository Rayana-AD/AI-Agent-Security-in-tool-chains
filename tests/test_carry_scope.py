"""Carry store scope and fresh-episode merge behavior."""

from __future__ import annotations

from bio_harness.provenance.accumulator import mark_reflection_drift
from bio_harness.provenance.accumulator import record_injection_detected
from bio_harness.provenance.carry_store import (
    merge_carry_states,
    prepare_carry_episode,
    resolve_carry_scope,
)
from bio_harness.provenance.constants import (
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_WATCH,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
)


def test_resolve_carry_scope_prefers_task_over_session():
    scope = resolve_carry_scope(
        {"session_id": "agentdojo", "suite": "banking", "user_task_id": "user_task_0"},
        query="pay bill",
    )
    assert scope == "agentdojo:banking:user_task_0"


def test_merge_carry_drops_stale_lockdown_on_fresh_episode():
    prev = mark_reflection_drift({}, reason="reflection_cross_node_mismatch")
    merged = merge_carry_states({}, prev, episode_id="ep1")
    assert merged.get(PROVENANCE_CARRY_LEVEL_KEY) == CARRY_LEVEL_WATCH
    assert "_provenance_reflection" not in merged


def test_resolve_carry_scope_ignores_stale_carry_scope_key():
    extra = {"carry_scope": "prompt:deadbeef", "session_id": "agentdojo"}
    scope = resolve_carry_scope(extra, query="different user task prompt")
    assert scope.startswith("prompt:")
    assert scope != "prompt:deadbeef"


def test_prepare_carry_episode_resets_in_memory_on_query_change():
    extra: dict = {"carry_scope": "prompt:deadbeef"}
    extra["_provenance_accum"] = record_injection_detected({})
    prepare_carry_episode(extra, query="task one")
    assert extra["_provenance_accum"].get(PROVENANCE_INJECTION_DETECTED_KEY)
    prepare_carry_episode(extra, query="task two")
    assert not extra["_provenance_accum"].get(PROVENANCE_INJECTION_DETECTED_KEY)
    assert resolve_carry_scope(extra, query="task two") != "prompt:deadbeef"
