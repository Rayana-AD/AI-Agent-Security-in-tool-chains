"""Cumulative provenance state for Idea1 partition / gate consumption."""

from __future__ import annotations

from typing import Any

from bio_harness.provenance.constants import (
    CARRY_LEVEL_ELEVATED,
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_NONE,
    CARRY_LEVEL_WATCH,
    GATE_TAG_ALIGNED,
    GATE_TAG_CONTROL,
    GATE_TAG_IPI_WATCH,
    GATE_TAG_REFLECTION,
    GATE_TAG_SHUFFLE,
    GATE_TAG_UNTRUSTED,
    LABEL_CONTROL_DRIFT,
    LABEL_UNTRUSTED_CARRY,
    PROVENANCE_BENIGN_STREAK_KEY,
    PROVENANCE_CARRY_KEY,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_CARRY_SCORE_DECAY,
    PROVENANCE_CARRY_THRESHOLD,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_GATE_TAG_KEY,
    PROVENANCE_GOAL_ALIGNED_KEY,
    PROVENANCE_HOP_COUNT_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_LABEL_KEY,
    PROVENANCE_REFLECTION_KEY,
    PROVENANCE_SCORE_KEY,
)
from bio_harness.cleave.scopes import (
    CAT_IPI_ENVELOPE,
    CAT_METADATA,
    CAT_STRICT,
    CAT_TRANSIT,
    CleaveScope,
)
from bio_harness.provenance.tool_sensitivity import exceeds_carry_ceiling


def _carry_level(global_store: dict[str, Any] | None) -> int:
    g = global_store or {}
    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY) or g.get(PROVENANCE_REFLECTION_KEY):
        return CARRY_LEVEL_LOCKDOWN
    return int(g.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)


def is_ipi_watch_only(global_store: dict[str, Any] | None) -> bool:
    """True when escalation is IPI-only at WATCH (no shuffle/reflection/elevated drift)."""
    g = global_store or {}
    if not g.get(PROVENANCE_INJECTION_DETECTED_KEY):
        return False
    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY) or g.get(PROVENANCE_REFLECTION_KEY):
        return False
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    if level > CARRY_LEVEL_WATCH:
        return False
    if g.get(PROVENANCE_DRIFT_KEY) and g.get(PROVENANCE_LABEL_KEY) == LABEL_CONTROL_DRIFT:
        return False
    return True


def is_ipi_benign_tool_eligible(global_store: dict[str, Any] | None) -> bool:
    """True when IPI contamination may proceed with any non-sensitive tool_call.

    Covers WATCH and ELEVATED (MLP untrusted_carry after IPI-light) but not
    LOCKDOWN from shuffle/reflection/heavy control_drift.
    """
    g = global_store or {}
    if not g.get(PROVENANCE_INJECTION_DETECTED_KEY):
        return False
    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY) or g.get(PROVENANCE_REFLECTION_KEY):
        return False
    if g.get(PROVENANCE_DRIFT_KEY) and g.get(PROVENANCE_LABEL_KEY) == LABEL_CONTROL_DRIFT:
        return False
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    return level < CARRY_LEVEL_LOCKDOWN


def _set_carry_level(g: dict[str, Any], level: int) -> None:
    prev = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    g[PROVENANCE_CARRY_LEVEL_KEY] = max(prev, level)
    if level >= CARRY_LEVEL_WATCH:
        g[PROVENANCE_CARRY_KEY] = True


def _set_gate_tag(g: dict[str, Any], tag: str) -> None:
    g[PROVENANCE_GATE_TAG_KEY] = tag


def _proposed_exceeds_ceiling(
    global_store: dict[str, Any] | None,
    *,
    proposed_tools: list[dict] | str | None = None,
    proposed_sensitive: bool | None = None,
) -> bool:
    if proposed_tools is not None:
        level = _carry_level(global_store)
        return exceeds_carry_ceiling(proposed_tools, carry_level=level)
    if proposed_sensitive is False:
        return False
    return proposed_sensitive is not False


def merge_provenance_tag(
    global_store: dict[str, Any] | None,
    *,
    drift_score: float,
    label: str,
    block_recommended: bool,
    node: str,
    proposed_tools: list[dict] | str | None = None,
) -> dict[str, Any]:
    """Merge tag into cumulative provenance (max score, graduated carry level)."""
    g = dict(global_store or {})
    prev = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
    g[PROVENANCE_SCORE_KEY] = max(prev, float(drift_score))
    g[PROVENANCE_LABEL_KEY] = label
    prev_level = _carry_level(g)
    midtier_ok = (
        node == "tool_call"
        and proposed_tools is not None
        and not exceeds_carry_ceiling(proposed_tools, carry_level=prev_level)
        and prev_level < CARRY_LEVEL_LOCKDOWN
    )

    if label == LABEL_CONTROL_DRIFT or block_recommended:
        if not midtier_ok:
            _set_carry_level(g, CARRY_LEVEL_LOCKDOWN)
            g[PROVENANCE_DRIFT_KEY] = True
            _set_gate_tag(g, GATE_TAG_CONTROL)
    elif label == LABEL_UNTRUSTED_CARRY or drift_score >= PROVENANCE_CARRY_THRESHOLD:
        _set_carry_level(g, CARRY_LEVEL_ELEVATED)
        _set_gate_tag(g, GATE_TAG_UNTRUSTED)
    else:
        if not g.get(PROVENANCE_GATE_TAG_KEY):
            _set_gate_tag(g, GATE_TAG_ALIGNED)

    if drift_score >= prev:
        g["_provenance_peak_node"] = node

    g[PROVENANCE_HOP_COUNT_KEY] = int(g.get(PROVENANCE_HOP_COUNT_KEY, 0) or 0) + 1
    return g


def mark_feature_shuffle_drift(global_store: dict[str, Any] | None, *, reason: str = "") -> dict[str, Any]:
    g = dict(global_store or {})
    g[PROVENANCE_FEATURE_SHUFFLE_KEY] = reason or True
    g[PROVENANCE_DRIFT_KEY] = True
    g[PROVENANCE_LABEL_KEY] = LABEL_CONTROL_DRIFT
    _set_carry_level(g, CARRY_LEVEL_LOCKDOWN)
    _set_gate_tag(g, GATE_TAG_SHUFFLE)
    return g


def mark_reflection_drift(global_store: dict[str, Any] | None, *, reason: str = "") -> dict[str, Any]:
    g = dict(global_store or {})
    g[PROVENANCE_REFLECTION_KEY] = reason or True
    g[PROVENANCE_DRIFT_KEY] = True
    g[PROVENANCE_LABEL_KEY] = LABEL_CONTROL_DRIFT
    _set_carry_level(g, CARRY_LEVEL_LOCKDOWN)
    _set_gate_tag(g, GATE_TAG_REFLECTION)
    return g


def should_block_at_boundary(
    global_store: dict[str, Any] | None,
    *,
    node: str,
    threshold: float,
    current_score: float | None = None,
    proposed_sensitive: bool | None = None,
    proposed_tools: list[dict] | str | None = None,
    carry_tiered: bool = True,
) -> tuple[bool, str]:
    """Block at tool boundary using graduated carry + current-node score."""
    if node not in ("tool_call", "tool_output"):
        return False, ""

    g = global_store or {}
    level = _carry_level(g)

    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY):
        reason = g.get(PROVENANCE_FEATURE_SHUFFLE_KEY)
        if isinstance(reason, str) and reason:
            return True, f"provenance_{reason}"
        return True, "provenance_feature_shuffle_drift"

    if g.get(PROVENANCE_REFLECTION_KEY):
        reason = g.get(PROVENANCE_REFLECTION_KEY)
        if isinstance(reason, str) and reason:
            return True, f"reflection_{reason}"
        return True, "reflection_drift"

    max_score = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
    boundary_score = float(current_score) if current_score is not None else max_score

    if carry_tiered and level == CARRY_LEVEL_WATCH and node == "tool_call":
        if proposed_sensitive is False:
            if boundary_score >= threshold:
                return True, f"provenance_active_drift:score={boundary_score:.3f}"
            return False, ""
        if proposed_sensitive is True:
            return False, ""

    if carry_tiered and level == CARRY_LEVEL_ELEVATED and node == "tool_call":
        if proposed_sensitive is False:
            if boundary_score >= threshold:
                return True, f"provenance_elevated_drift:score={boundary_score:.3f}"
            return False, ""
        if (
            _proposed_exceeds_ceiling(
                g,
                proposed_tools=proposed_tools,
                proposed_sensitive=proposed_sensitive,
            )
            and max_score >= threshold
        ):
            return True, f"provenance_carry:score={max_score:.3f}"

    if g.get(PROVENANCE_CARRY_KEY) and max_score >= threshold:
        if node == "tool_call" and not _proposed_exceeds_ceiling(
            g,
            proposed_tools=proposed_tools,
            proposed_sensitive=proposed_sensitive,
        ):
            return False, ""
        return True, f"provenance_carry:score={max_score:.3f}"

    if g.get(PROVENANCE_DRIFT_KEY) and boundary_score >= threshold:
        return True, f"provenance_cumulative_drift:score={boundary_score:.3f}"

    if boundary_score >= threshold:
        return True, f"provenance_score:{boundary_score:.3f}"

    return False, ""


def is_channel_escalated(global_store: dict[str, Any] | None) -> bool:
    """True when upstream channel saw injection or provenance/reflection drift."""
    g = global_store or {}
    if g.get(PROVENANCE_INJECTION_DETECTED_KEY):
        return True
    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY):
        return True
    if g.get(PROVENANCE_REFLECTION_KEY):
        return True
    if g.get(PROVENANCE_DRIFT_KEY):
        return True
    if g.get(PROVENANCE_CARRY_KEY):
        score = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
        return score >= PROVENANCE_CARRY_THRESHOLD
    return False


def record_injection_detected(global_store: dict[str, Any] | None, *, light: bool = False) -> dict[str, Any]:
    """Mark IPI envelope at tool_output; WATCH-level escalation (not full lockdown)."""
    g = dict(global_store or {})
    g[PROVENANCE_INJECTION_DETECTED_KEY] = True
    _set_carry_level(g, CARRY_LEVEL_WATCH)
    g[PROVENANCE_BENIGN_STREAK_KEY] = 0
    g[PROVENANCE_HOP_COUNT_KEY] = int(g.get(PROVENANCE_HOP_COUNT_KEY, 0) or 0) + 1
    if light:
        prev = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
        g[PROVENANCE_SCORE_KEY] = max(prev, 0.22)
        g[PROVENANCE_LABEL_KEY] = LABEL_UNTRUSTED_CARRY
        g["_provenance_trust"] = min(float(g.get("_provenance_trust", 1.0) or 1.0), 0.55)
        _set_gate_tag(g, GATE_TAG_UNTRUSTED)
    else:
        g[PROVENANCE_DRIFT_KEY] = True
        prev = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
        g[PROVENANCE_SCORE_KEY] = max(prev, 0.55)
        g[PROVENANCE_LABEL_KEY] = LABEL_CONTROL_DRIFT
        _set_gate_tag(g, GATE_TAG_IPI_WATCH)
    return g


def _decay_score_only(g: dict[str, Any], *, factor: float = 1.0) -> None:
    level = _carry_level(g)
    if level >= CARRY_LEVEL_LOCKDOWN:
        return
    score = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
    if score <= 0.0:
        return
    g[PROVENANCE_SCORE_KEY] = max(0.0, score - PROVENANCE_CARRY_SCORE_DECAY * factor)


def apply_cleave_carry_feedback(
    global_store: dict[str, Any] | None,
    *,
    stripped_categories: list[str] | None = None,
    cleave_scope: str = CleaveScope.NONE.value,
    cleave_applied: bool = False,
) -> dict[str, Any]:
    """Fold carry ↔ cleave feedback: what was trimmed adjusts escalation pressure."""
    g = dict(global_store or {})
    level = _carry_level(g)
    if level >= CARRY_LEVEL_LOCKDOWN:
        return g

    cats = set(stripped_categories or [])
    if (
        cleave_applied
        and cleave_scope != CleaveScope.NONE.value
        and not cats
    ):
        g[PROVENANCE_BENIGN_STREAK_KEY] = 0
        return g

    if CAT_IPI_ENVELOPE in cats:
        _decay_score_only(g, factor=1.25)
        streak = int(g.get(PROVENANCE_BENIGN_STREAK_KEY, 0)) + 1
        g[PROVENANCE_BENIGN_STREAK_KEY] = streak
        if float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0) < 0.18:
            _set_gate_tag(g, GATE_TAG_IPI_WATCH)
        return g

    if cats.intersection({CAT_TRANSIT, CAT_METADATA, CAT_STRICT}):
        _decay_score_only(g, factor=1.0)
        g[PROVENANCE_BENIGN_STREAK_KEY] = int(g.get(PROVENANCE_BENIGN_STREAK_KEY, 0)) + 1
    return g


def record_benign_tool_pass(
    global_store: dict[str, Any] | None,
    *,
    decay_streak: int = 3,
) -> dict[str, Any]:
    """Increment benign streak; score decay each pass; full clear after N clean boundaries."""
    g = dict(global_store or {})
    _decay_score_only(g)
    streak = int(g.get(PROVENANCE_BENIGN_STREAK_KEY, 0)) + 1
    g[PROVENANCE_BENIGN_STREAK_KEY] = streak
    if streak >= decay_streak:
        for k in (
            PROVENANCE_CARRY_KEY,
            PROVENANCE_CARRY_LEVEL_KEY,
            PROVENANCE_DRIFT_KEY,
            PROVENANCE_FEATURE_SHUFFLE_KEY,
            PROVENANCE_REFLECTION_KEY,
            PROVENANCE_INJECTION_DETECTED_KEY,
        ):
            g.pop(k, None)
        g[PROVENANCE_BENIGN_STREAK_KEY] = 0
        g[PROVENANCE_SCORE_KEY] = 0.0
    return g


def soften_tool_output_escalation(global_store: dict[str, Any] | None) -> dict[str, Any]:
    """Clean tool_output: slow score decay at WATCH; full soften when no injection."""
    g = dict(global_store or {})
    level = _carry_level(g)
    if g.get(PROVENANCE_INJECTION_DETECTED_KEY) and level <= CARRY_LEVEL_WATCH:
        _decay_score_only(g, factor=0.5)
        return g
    if g.get(PROVENANCE_INJECTION_DETECTED_KEY):
        return g
    if g.get(PROVENANCE_DRIFT_KEY) and g.get(PROVENANCE_LABEL_KEY) == LABEL_CONTROL_DRIFT:
        return g
    score = float(g.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0)
    if g.get(PROVENANCE_CARRY_KEY) and score >= PROVENANCE_CARRY_THRESHOLD:
        return g
    for k in (
        PROVENANCE_CARRY_KEY,
        PROVENANCE_CARRY_LEVEL_KEY,
        PROVENANCE_DRIFT_KEY,
        PROVENANCE_FEATURE_SHUFFLE_KEY,
        PROVENANCE_REFLECTION_KEY,
    ):
        g.pop(k, None)
    return g


def soften_reflection_lockdown(
    global_store: dict[str, Any] | None,
    *,
    reason: str = "goal_continuous",
) -> dict[str, Any]:
    """Downgrade reflection-only lockdown after field-grounded Continuity validation."""
    g = dict(global_store or {})
    g.pop(PROVENANCE_REFLECTION_KEY, None)
    if g.get(PROVENANCE_FEATURE_SHUFFLE_KEY):
        return g
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    if level >= CARRY_LEVEL_LOCKDOWN:
        g[PROVENANCE_CARRY_LEVEL_KEY] = CARRY_LEVEL_WATCH
        g[PROVENANCE_CARRY_KEY] = True
    if g.get(PROVENANCE_LABEL_KEY) == LABEL_CONTROL_DRIFT:
        if g.get(PROVENANCE_INJECTION_DETECTED_KEY):
            g[PROVENANCE_DRIFT_KEY] = True
            g[PROVENANCE_LABEL_KEY] = LABEL_UNTRUSTED_CARRY
            _set_gate_tag(g, GATE_TAG_IPI_WATCH)
        else:
            g.pop(PROVENANCE_DRIFT_KEY, None)
            g.pop(PROVENANCE_LABEL_KEY, None)
            _set_gate_tag(g, GATE_TAG_ALIGNED)
    g["_provenance_reflection_softened"] = reason
    return g


def record_goal_aligned_boundary(global_store: dict[str, Any] | None) -> dict[str, Any]:
    """Record a field-grounded goal-aligned action without clearing IPI evidence."""
    g = dict(global_store or {})
    g[PROVENANCE_GOAL_ALIGNED_KEY] = True
    g = soften_reflection_lockdown(g, reason="goal_aligned_boundary")
    _set_gate_tag(g, GATE_TAG_ALIGNED)
    _decay_score_only(g, factor=1.25)
    return g


def record_tool_boundary_block(global_store: dict[str, Any] | None) -> dict[str, Any]:
    g = dict(global_store or {})
    g[PROVENANCE_BENIGN_STREAK_KEY] = 0
    return g


def apply_to_partitioned_state(state, global_store: dict[str, Any]) -> None:
    """Write cumulative provenance into partition global store."""
    for k, v in global_store.items():
        if k.startswith("_provenance") or k in (
            PROVENANCE_SCORE_KEY,
            PROVENANCE_LABEL_KEY,
            PROVENANCE_DRIFT_KEY,
            PROVENANCE_CARRY_KEY,
            PROVENANCE_CARRY_LEVEL_KEY,
            PROVENANCE_FEATURE_SHUFFLE_KEY,
        ):
            state.merge_global_pollution(k, v)
