"""Channel escalation: injection at tool_output → block sensitive tool_call."""

from __future__ import annotations

from bio_harness.provenance.accumulator import record_injection_detected
from bio_harness.provenance.constants import (
    PROVENANCE_CARRY_KEY,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
)


def test_injection_detected_sets_escalation():
    out = record_injection_detected({})
    assert out.get(PROVENANCE_INJECTION_DETECTED_KEY)
    assert out.get(PROVENANCE_DRIFT_KEY)
    assert out.get(PROVENANCE_CARRY_KEY)


def test_ipi_simulate_blocks_second_sensitive_call():
    from eval.run_provenance_integration_ablation import _simulate_ipi

    row = _simulate_ipi("idea1_provenance_mlp")
    assert not row["first_tool_call_blocked"]
    assert row["tool_output_withheld"]
    assert row["second_tool_call_blocked"]
    assert row["injection_detected"] >= 1


def test_benign_tool_output_not_withheld():
    from eval.run_provenance_integration_ablation import _simulate_benign_tool_output

    row = _simulate_benign_tool_output("idea1_provenance_mlp")
    assert not row["withheld"]
    assert row["payload_visible"]
