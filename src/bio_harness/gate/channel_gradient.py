"""Channel gradient: passive downhill vs active uphill transport at Bio gate.

Biological mapping
------------------
- **Passive (high → low)**: dilution into trusted channel; no extra authorization.
- **Active (low → high)**: agent reaches outward (sensitive tool / state write); gate spends energy.
- **Blocked**: fold layer tagged lockdown; gate holds regardless of gradient.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bio_harness.provenance.accumulator import is_ipi_benign_tool_eligible
from bio_harness.provenance.tool_sensitivity import (
    carry_sensitivity_ceiling,
    tool_sensitivity_from_content,
)
from bio_harness.provenance.constants import (
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_WATCH,
    GATE_TAG_ALIGNED,
    GATE_TAG_CONTROL,
    GATE_TAG_IPI_WATCH,
    GATE_TAG_REFLECTION,
    GATE_TAG_SHUFFLE,
    GATE_TAG_UNTRUSTED,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_GATE_TAG_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_REFLECTION_KEY,
    SENSITIVE_TOOLS,
)

INFO_ENVELOPE_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")


@dataclass(frozen=True)
class ChannelGradient:
    mode: str  # passive | active | blocked
    reason: str = ""

    @property
    def needs_authorization(self) -> bool:
        return self.mode == "active"

    @property
    def is_passive(self) -> bool:
        return self.mode == "passive"


def _global_pollution(trusted: dict[str, Any] | None) -> dict[str, Any]:
    if not trusted:
        return {}
    g = trusted.get("_global_pollution")
    return g if isinstance(g, dict) else {}


def _tool_name_from_content(content: str) -> str:
    import json

    cl = content.lower()
    for name in SENSITIVE_TOOLS:
        if name in cl:
            return name
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return str(data.get("tool") or data.get("function") or "").lower()
    except json.JSONDecodeError:
        pass
    for part in re.findall(r'"tool"\s*:\s*"([^"]+)"', content, re.I):
        return part.lower()
    return ""


def _content_proposes_sensitive_tool(content: str) -> bool:
    name = _tool_name_from_content(content)
    return bool(name and name in SENSITIVE_TOOLS)


def assess_channel_gradient(
    content: str,
    *,
    node: str,
    trusted_snapshot: dict[str, Any] | None = None,
) -> ChannelGradient:
    """Classify transport direction for gate authorization cost."""
    g = _global_pollution(trusted_snapshot)
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, 0) or 0)
    gate_tag = str(g.get(PROVENANCE_GATE_TAG_KEY, "") or "")
    sensitive = _content_proposes_sensitive_tool(content)

    lockdown = (
        level >= CARRY_LEVEL_LOCKDOWN
        or bool(g.get(PROVENANCE_REFLECTION_KEY))
        or bool(g.get(PROVENANCE_FEATURE_SHUFFLE_KEY))
        or gate_tag in (GATE_TAG_REFLECTION, GATE_TAG_SHUFFLE, GATE_TAG_CONTROL)
        or (g.get(PROVENANCE_DRIFT_KEY) and gate_tag == GATE_TAG_CONTROL)
    )
    if lockdown and (sensitive or node == "tool_call"):
        return ChannelGradient("blocked", "fold_lockdown_uphill")

    if node == "tool_output":
        if gate_tag in ("", GATE_TAG_ALIGNED) and not g.get(PROVENANCE_INJECTION_DETECTED_KEY):
            return ChannelGradient("passive", "tool_output_downhill_clean")
        if g.get(PROVENANCE_INJECTION_DETECTED_KEY) and level < CARRY_LEVEL_LOCKDOWN:
            return ChannelGradient("passive", "tool_output_ipi_watch_dilution")
        if lockdown:
            return ChannelGradient("blocked", "tool_output_fold_hold")
        return ChannelGradient("active", "tool_output_suspicious_carry")

    if node == "tool_call":
        sens = tool_sensitivity_from_content(content)
        ceiling = carry_sensitivity_ceiling(level)
        if sens > 0 and sens <= ceiling and level == CARRY_LEVEL_WATCH:
            if g.get(PROVENANCE_INJECTION_DETECTED_KEY) or gate_tag in (
                GATE_TAG_IPI_WATCH,
                GATE_TAG_UNTRUSTED,
            ):
                return ChannelGradient("passive", "ipi_watch_midtier_downhill")
        if sens > 0 and sens > ceiling:
            return ChannelGradient("active", f"sens_{sens:.2f}_above_ceiling_{ceiling:.2f}")
        if _content_proposes_sensitive_tool(content):
            return ChannelGradient("active", "sensitive_tool_uphill")
        if gate_tag in (GATE_TAG_IPI_WATCH, GATE_TAG_UNTRUSTED) or g.get(PROVENANCE_INJECTION_DETECTED_KEY):
            if is_ipi_benign_tool_eligible(g):
                return ChannelGradient("passive", "ipi_benign_downhill")
            return ChannelGradient("active", "ipi_contaminated_uphill")
        if gate_tag in ("", GATE_TAG_ALIGNED):
            return ChannelGradient("passive", "benign_tool_downhill")
        return ChannelGradient("active", f"carry_tag_uphill:{gate_tag}")

    return ChannelGradient("passive", "non_tool_boundary")
