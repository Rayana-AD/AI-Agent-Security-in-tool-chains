"""Continuity orchestration profile resolution."""

from __future__ import annotations

from bio_harness.harness.config import HarnessConfig
from bio_harness.harness.continuity import ORCHESTRATION_FOLD_GATE_CLEAVE, resolve_continuity


def test_fold_gate_cleave_profile():
    cfg = HarnessConfig(
        name="bio_04",
        continuity_orchestration=ORCHESTRATION_FOLD_GATE_CLEAVE,
        use_cleave=False,
        agentdojo_ipi_output_mode="withhold",
        provenance_reflection_watch_carveout=False,
    )
    p = resolve_continuity(cfg)
    assert p.ipi_output_mode == "metadata_strip"
    assert p.reflection_continuity is True
    assert p.ipi_light is True
    assert p.per_tool_filter is True
    assert p.task_fidelity_hint is True
    assert p.use_cleave is True


def test_legacy_flags_when_no_orchestration():
    cfg = HarnessConfig(
        name="meta_watch",
        provenance_reflection_watch_carveout=True,
        provenance_ipi_light_state=False,
        provenance_per_tool_filter=True,
        agentdojo_ipi_output_mode="metadata_strip",
        use_cleave=False,
    )
    p = resolve_continuity(cfg)
    assert p.reflection_continuity is True
    assert p.ipi_light is False
    assert p.use_cleave is False
