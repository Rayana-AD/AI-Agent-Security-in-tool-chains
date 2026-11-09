"""Graduated carry levels + cross-session CarryStore."""

from __future__ import annotations

import time

from bio_harness.provenance.accumulator import (
    is_ipi_benign_tool_eligible,
    is_ipi_watch_only,
    merge_provenance_tag,
    record_benign_tool_pass,
    record_injection_detected,
    should_block_at_boundary,
)
from bio_harness.provenance.carry_store import FileCarryStore, merge_carry_states, resolve_carry_scope
from bio_harness.provenance.constants import (
    CARRY_LEVEL_ELEVATED,
    CARRY_LEVEL_WATCH,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_SCORE_KEY,
)


def test_injection_watch_allows_benign_tool_call():
    accum = record_injection_detected({})
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_WATCH
    block, reason = should_block_at_boundary(
        accum,
        node="tool_call",
        threshold=0.20,
        current_score=0.05,
        proposed_sensitive=False,
        carry_tiered=True,
    )
    assert block is False, reason


def test_injection_watch_blocks_sensitive_via_escalation_not_carry():
    accum = record_injection_detected({})
    block, _ = should_block_at_boundary(
        accum,
        node="tool_call",
        threshold=0.20,
        current_score=0.05,
        proposed_sensitive=True,
        carry_tiered=True,
    )
    assert block is False


def test_elevated_carry_blocks_sensitive_on_stale_score():
    accum = merge_provenance_tag(
        {},
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="review",
    )
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_ELEVATED
    block, reason = should_block_at_boundary(
        accum,
        node="tool_call",
        threshold=0.20,
        current_score=0.05,
        proposed_sensitive=True,
        carry_tiered=True,
    )
    assert block is True
    assert "carry" in reason


def test_elevated_carry_allows_benign_when_current_score_low():
    accum = merge_provenance_tag(
        {},
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="review",
    )
    block, _ = should_block_at_boundary(
        accum,
        node="tool_call",
        threshold=0.20,
        current_score=0.05,
        proposed_sensitive=False,
        carry_tiered=True,
    )
    assert block is False


def test_benign_pass_streak_clears_watch_injection():
    accum = record_injection_detected({})
    for _ in range(3):
        accum = record_benign_tool_pass(accum, decay_streak=3)
    assert not accum.get(PROVENANCE_INJECTION_DETECTED_KEY)
    assert float(accum.get(PROVENANCE_SCORE_KEY, 0)) == 0.0


def test_carry_store_persists_and_merges_across_episodes(tmp_path):
    store = FileCarryStore(cache_dir=tmp_path, ttl_seconds=3600)
    scope = "workspace:user_task_32"
    store.save(scope, record_injection_detected({}))
    ep2 = store.merge_episode(scope, {}, episode_id="run_b")
    assert ep2.get(PROVENANCE_INJECTION_DETECTED_KEY)
    assert ep2[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_WATCH


def test_carry_store_expires(tmp_path):
    store = FileCarryStore(cache_dir=tmp_path, ttl_seconds=0.01)
    scope = "ttl_test"
    store.save(scope, record_injection_detected({}))
    time.sleep(0.02)
    assert store.load(scope) == {}


def test_resolve_carry_scope_prefers_explicit():
    assert resolve_carry_scope({"carry_scope": "custom"}) == "custom"
    assert resolve_carry_scope({"suite": "ws", "user_task": "user_task_32"}) == "ws:user_task_32"


def test_ipi_benign_eligible_at_elevated_not_watch_only():
    accum = record_injection_detected({}, light=True)
    accum = merge_provenance_tag(
        accum,
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="tool_output",
    )
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_ELEVATED
    assert not is_ipi_watch_only(accum)
    assert is_ipi_benign_tool_eligible(accum)


def test_gate_allows_non_sensitive_elevated_carry_without_ipi():
    from bio_harness.gate.predicates import _detect_provenance_drift

    accum = merge_provenance_tag(
        {},
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="review",
    )
    trusted = {"_global_pollution": accum}
    assert not _detect_provenance_drift(
        '{"tool": "get_user_information", "args": {}}',
        trusted,
        node="tool_call",
    )


def test_gate_allows_non_sensitive_tools_after_ipi_elevated():
    from bio_harness.gate.predicates import _detect_provenance_drift

    accum = record_injection_detected({}, light=True)
    accum = merge_provenance_tag(
        accum,
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="tool_output",
    )
    trusted = {"_global_pollution": accum}
    for tool in (
        "get_hotels_address",
        "get_current_day",
        "create_calendar_event",
        "get_file_by_id",
        "get_user_information",
    ):
        blob = f'{{"tool": "{tool}", "args": {{}}}}'
        assert not _detect_provenance_drift(blob, trusted, node="tool_call"), tool
    assert _detect_provenance_drift(
        '{"tool": "send_email", "args": {"recipients": ["a@b.com"]}}',
        trusted,
        node="tool_call",
    )
