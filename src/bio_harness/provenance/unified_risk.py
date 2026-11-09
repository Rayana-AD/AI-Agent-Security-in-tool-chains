"""Unified continuous risk — deprecated; fold layer uses tag-based block only."""

from __future__ import annotations

import json
from typing import Any

# Base sensitivity by tool name (continuous in [0, 1]).
_BASE_SENS: dict[str, float] = {
    "send_email": 1.0,
    "send_money": 1.0,
    "transfer_money": 1.0,
    "share_file": 0.75,
    "delete_file": 0.85,
    "post_webpage": 0.7,
    "invite_user_to_slack": 0.65,
    "remove_user_from_slack": 0.65,
    "add_user_to_channel": 0.65,
    "send_channel_message": 0.8,
    "send_direct_message": 0.8,
    "update_scheduled_transaction": 0.9,
    "reserve_hotel": 0.5,
}

# Default weights (fixed; tuning via audit scripts, not extra inference).
_W_MLP = 0.35
_W_REFL = 0.30
_W_IPI = 0.25
_W_SENS = 0.40


def _tool_items(proposed_tools: list[dict] | str | None) -> list[dict]:
    if proposed_tools is None:
        return []
    if isinstance(proposed_tools, str):
        try:
            data = json.loads(proposed_tools)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            return []
        return []
    return [x for x in proposed_tools if isinstance(x, dict)]


def _tool_name(item: dict) -> str:
    return (item.get("tool") or item.get("function") or "").lower()


def base_tool_sensitivity(proposed_tools: list[dict] | str | None) -> float:
    """Max base sensitivity across proposed tools."""
    sens = 0.0
    for item in _tool_items(proposed_tools):
        name = _tool_name(item)
        sens = max(sens, _BASE_SENS.get(name, 0.0))
    return sens


def trust_from_accum(accum: dict[str, Any] | None) -> float:
    """Map carry/injection state to trust T in [0, 1] (derived, not stored)."""
    g = accum or {}
    if g.get("_provenance_trust") is not None:
        return max(0.0, min(1.0, float(g["_provenance_trust"])))
    level = int(g.get("_provenance_carry_level", 0) or 0)
    if g.get("_provenance_feature_shuffle") or g.get("_provenance_reflection"):
        return 0.05
    if level >= 3:
        return 0.1
    if level >= 2:
        return 0.35
    if g.get("_provenance_injection_detected"):
        return 0.55
    if level >= 1:
        return 0.65
    score = float(g.get("_provenance_score", 0.0) or 0.0)
    return max(0.0, min(1.0, 1.0 - score))


def ipi_strength_from_trust(trust: float) -> float:
    return max(0.0, min(1.0, 1.0 - trust))


def boundary_threshold(sens: float) -> float:
    """Lower threshold for more sensitive actions."""
    return max(0.25, 0.48 - 0.18 * sens)


def compute_boundary_risk(
    *,
    mlp_score: float,
    reflection_score: float,
    trust: float,
    tool_sensitivity: float,
) -> float:
    s_ipi = ipi_strength_from_trust(trust)
    r = (
        _W_MLP * max(0.0, min(1.0, mlp_score))
        + _W_REFL * max(0.0, min(1.0, reflection_score))
        + _W_IPI * s_ipi
        + _W_SENS * max(0.0, min(1.0, tool_sensitivity))
    )
    return max(0.0, min(1.0, r))


def unified_should_block(
    *,
    mlp_score: float,
    reflection_score: float,
    reflection_recommended: bool,
    accum: dict[str, Any] | None,
    proposed_tools: list[dict] | str | None,
    feature_shuffle_failed: bool = False,
) -> tuple[bool, str, float]:
    """Hard decision from continuous risk R (inference cost: a few FLOPs)."""
    sens = base_tool_sensitivity(proposed_tools)
    if feature_shuffle_failed and sens > 0.0:
        return True, "provenance_feature_shuffle_drift", 1.0

    if feature_shuffle_failed and sens <= 0.0:
        feature_shuffle_failed = False

    trust = trust_from_accum(accum)
    refl = reflection_score if reflection_recommended else 0.0
    risk = compute_boundary_risk(
        mlp_score=mlp_score,
        reflection_score=refl,
        trust=trust,
        tool_sensitivity=sens,
    )
    tau = boundary_threshold(sens)
    if risk > tau:
        if sens >= 0.7:
            reason = f"unified_risk:sensitive:R={risk:.3f}>τ={tau:.3f}"
        elif reflection_recommended:
            reason = f"unified_risk:reflection:R={risk:.3f}>τ={tau:.3f}"
        else:
            reason = f"unified_risk:R={risk:.3f}>τ={tau:.3f}"
        return True, reason, risk
    return False, "", risk
