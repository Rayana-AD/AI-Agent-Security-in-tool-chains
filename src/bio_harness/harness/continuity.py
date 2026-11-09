"""Continuity / AgentDojo orchestration profiles (replaces stacked ablation flags)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bio_harness.harness.config import HarnessConfig

ORCHESTRATION_FOLD_GATE_CLEAVE = "fold_gate_cleave"


@dataclass(frozen=True)
class ContinuityProfile:
    """Effective continuity behavior after resolving orchestration mode."""

    ipi_output_mode: str
    reflection_continuity: bool
    ipi_light: bool
    per_tool_filter: bool
    task_fidelity_hint: bool
    use_cleave: bool


def resolve_continuity(cfg: HarnessConfig) -> ContinuityProfile:
    """Map config → runtime continuity profile.

    ``fold_gate_cleave`` is the post-refactor default for meta_full:
    IPI → Fold → Gate → Cleave, reflection path continuity, no lockdown ratchet on reads.
    Legacy ablation configs keep explicit per-flag control when orchestration is unset.
    """
    mode = getattr(cfg, "continuity_orchestration", None)
    if mode == ORCHESTRATION_FOLD_GATE_CLEAVE:
        return ContinuityProfile(
            ipi_output_mode="metadata_strip",
            reflection_continuity=True,
            ipi_light=True,
            per_tool_filter=True,
            task_fidelity_hint=True,
            use_cleave=True,
        )
    return ContinuityProfile(
        ipi_output_mode=str(getattr(cfg, "agentdojo_ipi_output_mode", "withhold")),
        reflection_continuity=bool(getattr(cfg, "provenance_reflection_watch_carveout", False)),
        ipi_light=bool(getattr(cfg, "provenance_ipi_light_state", False)),
        per_tool_filter=bool(getattr(cfg, "provenance_per_tool_filter", False)),
        task_fidelity_hint=bool(getattr(cfg, "provenance_task_fidelity_hint", False)),
        use_cleave=bool(getattr(cfg, "use_cleave", False)),
    )
