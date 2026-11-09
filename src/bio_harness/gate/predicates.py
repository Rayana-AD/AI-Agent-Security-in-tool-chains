"""Gate predicates: hard rules + optional LLM judge."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bio_harness.llm.base import LLMBackend
from bio_harness.gate.channel_gradient import assess_channel_gradient
from bio_harness.provenance.accumulator import is_ipi_benign_tool_eligible
from bio_harness.provenance.tool_sensitivity import exceeds_carry_ceiling
from bio_harness.provenance.constants import (
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_WATCH,
    GATE_TAG_CONTROL,
    GATE_TAG_IPI_WATCH,
    GATE_TAG_REFLECTION,
    GATE_TAG_SHUFFLE,
    GATE_TAG_UNTRUSTED,
    LABEL_CONTROL_DRIFT,
    PROVENANCE_CARRY_KEY,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_GATE_TAG_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_LABEL_KEY,
    PROVENANCE_REFLECTION_KEY,
    SENSITIVE_TOOLS,
)


HARMFUL_PATTERNS = [
    re.compile(r"(?i)ignore (all )?(previous )?(instructions|constraints|safety)"),
    re.compile(r"(?i)bypass (the )?(safety|checks|guard)"),
    re.compile(r"(?i)send (all|every) (email|data|file)"),
    re.compile(r"(?i)exfiltrate"),
    re.compile(r"(?i)run (malicious|arbitrary) code"),
    re.compile(r"(?i)override (security|guard|safety)"),
    re.compile(r"(?i)hidden harmful"),
]


@dataclass
class GateResult:
    passed: bool
    reason: str = ""
    layer: str = "gate"
    gradient_mode: str = ""


class GatePredicate:
    def __init__(
        self,
        llm: LLMBackend | None = None,
        strict: bool = False,
        use_llm_judge: bool = False,
    ) -> None:
        self.llm = llm
        self.strict = strict
        self.use_llm_judge = use_llm_judge

    def check(
        self,
        content: str,
        *,
        node: str,
        user_goal: str = "",
        trusted_snapshot: dict[str, Any] | None = None,
    ) -> GateResult:
        gradient = assess_channel_gradient(
            content,
            node=node,
            trusted_snapshot=trusted_snapshot,
        )

        for pat in HARMFUL_PATTERNS:
            if pat.search(content):
                return GateResult(
                    passed=False,
                    reason=f"harmful_pattern:{pat.pattern}",
                    layer="gate",
                    gradient_mode=gradient.mode,
                )

        if self.strict and re.search(r"(?i)(_routing_hint|signal_peptide|gate_token)", content):
            return GateResult(
                passed=False,
                reason="transit_field_in_strict_mode",
                layer="gate",
                gradient_mode=gradient.mode,
            )

        if trusted_snapshot and _detect_state_pollution(content, trusted_snapshot):
            return GateResult(
                passed=False,
                reason="state_pollution_detected",
                layer="gate",
                gradient_mode=gradient.mode,
            )

        # Passive downhill: fold layer already aligned — gate does not re-score carry.
        if gradient.is_passive:
            if self.use_llm_judge and self.llm and user_goal and gradient.needs_authorization:
                harmful, reason, _ = self.llm.judge_harmful(user_goal, content)
                if harmful:
                    return GateResult(
                        passed=False,
                        reason=f"llm_judge:{reason}",
                        layer="gate",
                        gradient_mode=gradient.mode,
                    )
            if node == "tool_call" and not _valid_tool_call(content):
                return GateResult(
                    passed=False,
                    reason="invalid_tool_call_format",
                    layer="gate",
                    gradient_mode=gradient.mode,
                )
            return GateResult(passed=True, layer="gate", gradient_mode=gradient.mode)

        if gradient.mode == "blocked":
            return GateResult(
                passed=False,
                reason=f"channel_blocked:{gradient.reason}",
                layer="gate",
                gradient_mode=gradient.mode,
            )

        # Active uphill: fold carry tags authorize or gate holds.
        if trusted_snapshot and _detect_provenance_drift(
            content,
            trusted_snapshot,
            node=node,
        ):
            return GateResult(
                passed=False,
                reason="provenance_drift_detected",
                layer="gate",
                gradient_mode=gradient.mode,
            )

        if self.use_llm_judge and self.llm and user_goal:
            harmful, reason, _ = self.llm.judge_harmful(user_goal, content)
            if harmful:
                return GateResult(passed=False, reason=f"llm_judge:{reason}", layer="gate", gradient_mode=gradient.mode)

        if node == "tool_call" and not _valid_tool_call(content):
            return GateResult(
                passed=False,
                reason="invalid_tool_call_format",
                layer="gate",
                gradient_mode=gradient.mode,
            )

        return GateResult(passed=True, layer="gate", gradient_mode=gradient.mode)


def _detect_state_pollution(content: str, trusted: dict[str, Any]) -> bool:
    """Detect attempts to rewrite trusted facts via hidden markers."""
    if "_routing_hint" in content.lower() and trusted.get("approved_facts"):
        if "override" in content.lower() or "ignore previous" in content.lower():
            return True
    return False


def _global_pollution(trusted: dict[str, Any]) -> dict[str, Any]:
    g = trusted.get("_global_pollution")
    if isinstance(g, dict):
        return g
    return {}


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


def _allows_non_sensitive_tool_call(
    g: dict[str, Any],
    *,
    node: str,
    sensitive: bool,
) -> bool:
    """Non-sensitive tool_call may proceed unless reflection lockdown is active."""
    if node != "tool_call" or sensitive:
        return False
    if g.get(PROVENANCE_REFLECTION_KEY):
        return False
    return True


def _exceeds_carry_tier(content: str, g: dict[str, Any], *, node: str) -> bool:
    if node != "tool_call":
        return False
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, 0) or 0)
    return exceeds_carry_ceiling(None, carry_level=level, content=content)


def _detect_provenance_drift(
    content: str,
    trusted: dict[str, Any],
    *,
    node: str,
) -> bool:
    """Block from discrete carry/gate tags — no score recompute at Bio gate."""
    if node not in ("tool_call", "tool_output"):
        return False
    g = _global_pollution(trusted)
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, 0) or 0)
    sensitive = _content_proposes_sensitive_tool(content)
    gate_tag = g.get(PROVENANCE_GATE_TAG_KEY, "")

    if _allows_non_sensitive_tool_call(g, node=node, sensitive=sensitive):
        return False

    if node == "tool_call" and not sensitive and is_ipi_benign_tool_eligible(g):
        return False

    if node == "tool_output":
        if g.get(PROVENANCE_INJECTION_DETECTED_KEY) and level < CARRY_LEVEL_LOCKDOWN:
            return False
        if not g.get(PROVENANCE_FEATURE_SHUFFLE_KEY) and not g.get(PROVENANCE_REFLECTION_KEY):
            return False

    if g.get(PROVENANCE_REFLECTION_KEY) or gate_tag == GATE_TAG_REFLECTION:
        return level >= CARRY_LEVEL_LOCKDOWN or _exceeds_carry_tier(content, g, node=node)

    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY) or gate_tag == GATE_TAG_SHUFFLE:
        return _exceeds_carry_tier(content, g, node=node)

    if g.get(PROVENANCE_INJECTION_DETECTED_KEY) or gate_tag in (GATE_TAG_IPI_WATCH, GATE_TAG_UNTRUSTED):
        return _exceeds_carry_tier(content, g, node=node)

    if g.get(PROVENANCE_DRIFT_KEY) and g.get(PROVENANCE_LABEL_KEY) == LABEL_CONTROL_DRIFT:
        return level >= CARRY_LEVEL_LOCKDOWN or _exceeds_carry_tier(content, g, node=node)

    if gate_tag == GATE_TAG_CONTROL:
        return level >= CARRY_LEVEL_LOCKDOWN or _exceeds_carry_tier(content, g, node=node)

    if g.get(PROVENANCE_CARRY_KEY) and gate_tag == GATE_TAG_UNTRUSTED:
        return _exceeds_carry_tier(content, g, node=node)

    return False


def _valid_tool_call(content: str) -> bool:
    cl = content.lower()
    if "tool:" in cl or "action:" in cl or "read_file" in cl or "send_email" in cl:
        return True
    return len(content.strip()) > 10
