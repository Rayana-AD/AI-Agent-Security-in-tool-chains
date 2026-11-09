"""Tests for channel gradient and situational cleave policy."""

from __future__ import annotations

from bio_harness.gate.channel_gradient import assess_channel_gradient
from bio_harness.gate.predicates import GatePredicate
from bio_harness.provenance.accumulator import mark_reflection_drift, record_injection_detected
from bio_harness.provenance.cleave_policy import should_cleave
from bio_harness.provenance.constants import GATE_TAG_ALIGNED, PROVENANCE_GATE_TAG_KEY


def test_passive_downhill_benign_tool_call():
    g = assess_channel_gradient(
        'tool: read_file\nargs: {"path": "public.txt"}',
        node="tool_call",
        trusted_snapshot={"_global_pollution": {PROVENANCE_GATE_TAG_KEY: GATE_TAG_ALIGNED}},
    )
    assert g.is_passive


def test_active_uphill_sensitive_tool():
    g = assess_channel_gradient(
        'tool: send_email\nargs: {"to": "a@b.com"}',
        node="tool_call",
        trusted_snapshot={"_global_pollution": {PROVENANCE_GATE_TAG_KEY: GATE_TAG_ALIGNED}},
    )
    assert g.needs_authorization


def test_blocked_lockdown_sensitive():
    accum = mark_reflection_drift({}, reason="reflection_cross_node_mismatch")
    g = assess_channel_gradient(
        'tool: send_money\nargs: {"amount": 10}',
        node="tool_call",
        trusted_snapshot={"_global_pollution": accum},
    )
    assert g.mode == "blocked"


def test_gate_passive_skips_carry_rescore():
    gate = GatePredicate()
    result = gate.check(
        "Meeting notes summary for Q3 planning.",
        node="tool_output",
        trusted_snapshot={"_global_pollution": {PROVENANCE_GATE_TAG_KEY: GATE_TAG_ALIGNED}},
    )
    assert result.passed
    assert result.gradient_mode == "passive"


def test_gate_active_blocks_sensitive_under_ipi():
    accum = record_injection_detected({})
    gate = GatePredicate()
    result = gate.check(
        'tool: send_email\nargs: {"to": "x@y.com", "body": "hi"}',
        node="tool_call",
        trusted_snapshot={"_global_pollution": accum},
    )
    assert not result.passed
    assert result.gradient_mode == "active"


def test_should_cleave_only_with_signal():
    clean = "Quarterly revenue grew 12% year over year."
    do, reason, scope = should_cleave(clean, accum={}, cleave_enabled=True)
    assert not do
    assert reason == "no_cleave_signal"
    assert scope.value == "none"

    transit = "facts ok\nsignal_peptide: route_bypass\nplan: proceed"
    do2, reason2, scope2 = should_cleave(transit, accum={}, cleave_enabled=True)
    assert do2
    assert reason2 == "transit_signal_present"

    ipi = "data\n<INFORMATION> inject </INFORMATION>"
    do3, _, scope3 = should_cleave(ipi, accum=record_injection_detected({}), cleave_enabled=True)
    assert do3
    assert scope3.value == "transit"
