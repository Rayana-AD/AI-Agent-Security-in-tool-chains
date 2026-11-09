"""Graduated tool sensitivity ceilings at carry levels."""

from __future__ import annotations

from bio_harness.gate.predicates import _detect_provenance_drift
from bio_harness.provenance.accumulator import record_injection_detected
from bio_harness.provenance.tool_sensitivity import (
    carry_sensitivity_ceiling,
    configure_carry_ceiling,
    exceeds_carry_ceiling,
    tool_sensitivity,
)


def test_watch_ceiling_allows_share_blocks_send_email():
    configure_carry_ceiling(table=None, enabled=True)
    level = 1  # WATCH
    assert carry_sensitivity_ceiling(level) == 0.85
    assert tool_sensitivity("share_file") == 0.75
    assert tool_sensitivity("send_email") == 1.0
    assert not exceeds_carry_ceiling(
        [{"tool": "share_file", "args": {}}],
        carry_level=level,
    )
    assert exceeds_carry_ceiling(
        [{"tool": "send_email", "args": {}}],
        carry_level=level,
    )


def test_elevated_ceiling_blocks_share_and_send():
    configure_carry_ceiling(table=None, enabled=True)
    level = 2
    assert not exceeds_carry_ceiling(
        [{"tool": "reserve_hotel", "args": {}}],
        carry_level=level,
    )
    assert exceeds_carry_ceiling(
        [{"tool": "share_file", "args": {}}],
        carry_level=level,
    )
    assert exceeds_carry_ceiling(
        [{"tool": "send_email", "args": {}}],
        carry_level=level,
    )


def test_gate_drift_allows_share_at_ipi_watch():
    configure_carry_ceiling(table=None, enabled=True)
    accum = record_injection_detected({}, light=True)
    trusted = {"_global_pollution": accum}
    share = '{"tool": "share_file", "args": {"id": "7", "permission": "read"}}'
    send = '{"tool": "send_email", "args": {"recipients": ["a@b.com"]}}'
    assert not _detect_provenance_drift(share, trusted, node="tool_call")
    assert _detect_provenance_drift(send, trusted, node="tool_call")
