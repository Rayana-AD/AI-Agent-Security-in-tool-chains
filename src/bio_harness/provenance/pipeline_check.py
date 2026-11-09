"""Shared fold-layer pipeline: reflection → feature-shuffle → tagger → block."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from bio_harness.provenance.accumulator import (
    is_channel_escalated,
    is_ipi_benign_tool_eligible,
    mark_feature_shuffle_drift,
    mark_reflection_drift,
    record_goal_aligned_boundary,
    soften_reflection_lockdown,
)
from bio_harness.provenance.feature_shuffle import (
    CoherenceUnderFeatureShuffleChecker,
    FeatureShuffleResult,
)
from bio_harness.provenance.features import ProvenanceContext, context_from_node_outputs
from bio_harness.provenance.reflection_probe import (
    ReflectionProbe,
    ReflectionProbeResult,
    reflection_goal_continuous,
)
from bio_harness.provenance.constants import (
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_REFLECTION_KEY,
    SENSITIVE_TOOLS,
)
from bio_harness.provenance.path_patterns import is_sensitive_path
from bio_harness.provenance.tool_sensitivity import (
    carry_sensitivity_ceiling,
    exceeds_carry_ceiling,
    max_tool_sensitivity,
)
from bio_harness.provenance.tagger import ProvenanceTagger


@dataclass
class ProvenancePipelineResult:
    accum: dict[str, Any]
    prov_reason: str = ""
    prov_score: float = 0.0
    reflection_result: ReflectionProbeResult | None = None
    feature_shuffle_results: list[tuple[str, FeatureShuffleResult]] | None = None
    block: bool = False
    block_reason: str = ""
    block_layer: str = ""


def _tool_output_context(
    user_goal: str,
    node_outputs: dict[str, str],
    *,
    current_text: str = "",
    proposed_tools: str = "",
) -> ProvenanceContext:
    plan = node_outputs.get("plan", "")
    review = node_outputs.get("review", "")
    merged_review = f"{plan}\n{review}".strip() if plan else review
    tool_body = current_text.strip() or node_outputs.get("tool_call", "")
    return ProvenanceContext(
        user_goal=user_goal,
        review=merged_review,
        tool_context=tool_body,
        proposed_tools_json=proposed_tools,
        node="tool_output",
    )


def _has_embedded_tool_result(text: str) -> bool:
    tl = text.lower()
    return any(m in tl for m in ("result:", "tool output", "meeting notes", "assistant:"))


def _proposed_tools_str(proposed_tools: list[dict] | str | None) -> str:
    if proposed_tools is None:
        return ""
    if isinstance(proposed_tools, str):
        return proposed_tools
    import json

    return json.dumps(proposed_tools, ensure_ascii=False)


def _proposed_sensitive(proposed_tools: list[dict] | str | None) -> bool:
    if proposed_tools is None:
        return False
    if isinstance(proposed_tools, str):
        tl = proposed_tools.lower()
        if any(t in tl for t in SENSITIVE_TOOLS):
            return True
        for part in re.findall(r'["\']?path["\']?\s*:\s*["\']([^"\']+)', proposed_tools, re.I):
            if is_sensitive_path(part):
                return True
        return False
    for item in proposed_tools:
        if not isinstance(item, dict):
            continue
        name = (item.get("tool") or item.get("function") or "").lower()
        if name in SENSITIVE_TOOLS:
            return True
        args = item.get("args") or {}
        path = args.get("path") or args.get("file") or ""
        if isinstance(path, str) and is_sensitive_path(path):
            return True
    return False


def _effective_proposed_sensitive(
    proposed_tools: list[dict] | str | None,
) -> bool:
    return _proposed_sensitive(proposed_tools)


_GROUNDING_FIELDS: dict[str, tuple[str, ...]] = {
    "send_money": ("recipient",),
    "transfer_money": ("recipient",),
    "update_scheduled_transaction": ("id",),
    "send_email": ("recipients", "to"),
    "send_direct_message": ("recipient", "user"),
    "send_channel_message": ("channel",),
    "invite_user_to_slack": ("user", "email"),
    "remove_user_from_slack": ("user", "email"),
    "add_user_to_channel": ("user", "email", "channel"),
    # For sharing, the external principal is safety-critical; the file id may
    # be created within the current task and need not appear in the user text.
    "share_file": ("user", "email", "recipient"),
    "delete_file": ("path", "file", "id", "file_id"),
    "reserve_hotel": ("hotel", "hotel_name"),
    "post_webpage": ("url",),
}

_EXTERNAL_DESTINATION_TOOLS = frozenset(
    {
        "send_money",
        "transfer_money",
        "send_email",
        "send_direct_message",
        "send_channel_message",
        "invite_user_to_slack",
        "remove_user_from_slack",
        "add_user_to_channel",
        "share_file",
        "post_webpage",
    }
)


def _flatten_grounding_values(value: Any) -> list[str]:
    if isinstance(value, (str, int, float)):
        return [str(value).strip()]
    if isinstance(value, (list, tuple, set)):
        return [
            item
            for part in value
            for item in _flatten_grounding_values(part)
        ]
    return []


def _field_grounded_continuity(
    user_goal: str,
    node_outputs: dict[str, str],
    proposed_tools: list[dict] | str | None,
    *,
    lexical_continuity: bool,
) -> tuple[bool, str]:
    """Require sensitive destinations/objects to come from goal or cleaved tool evidence."""
    if not lexical_continuity:
        return False, "continuity_below_threshold"
    if proposed_tools is None:
        return False, "continuity_no_proposed_tool"
    items: list[dict]
    if isinstance(proposed_tools, str):
        try:
            parsed = json.loads(proposed_tools)
        except json.JSONDecodeError:
            return False, "continuity_unparseable_tool"
        items = parsed if isinstance(parsed, list) else [parsed]
    else:
        items = proposed_tools

    evidence = f"{user_goal}\n{node_outputs.get('trusted_tool_results', '')}".lower()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("tool") or item.get("function") or "").lower()
        fields = _GROUNDING_FIELDS.get(name)
        if not fields:
            continue
        args = item.get("args") or {}
        values = [
            (field, value)
            for field in fields
            for value in _flatten_grounding_values(args.get(field))
            if value
        ]
        if not values:
            return False, f"continuity_missing_grounding_field:{name}"
        for field, value in values:
            value_l = value.lower()
            if field in ("id", "file_id"):
                pattern = rf"\b(?:id|file_id)\s*[:=]\s*['\"]?{re.escape(value_l)}\b"
                if not re.search(pattern, evidence):
                    return False, f"continuity_ungrounded_field:{name}.{field}"
            elif value_l not in evidence:
                return False, f"continuity_ungrounded_field:{name}.{field}"
    return True, "goal_continuous_fields_grounded"


def _external_fields_grounded_in_goal(
    user_goal: str,
    proposed_tools: list[dict] | str | None,
) -> bool:
    """During active drift, external destinations must be explicit in the user goal."""
    if proposed_tools is None:
        return False
    if isinstance(proposed_tools, str):
        try:
            parsed = json.loads(proposed_tools)
        except json.JSONDecodeError:
            return False
        items = parsed if isinstance(parsed, list) else [parsed]
    else:
        items = proposed_tools
    goal_l = user_goal.lower()
    checked = False
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("tool") or item.get("function") or "").lower()
        if name not in _EXTERNAL_DESTINATION_TOOLS:
            continue
        checked = True
        args = item.get("args") or {}
        fields = _GROUNDING_FIELDS.get(name, ())
        values = [
            value.lower()
            for field in fields
            for value in _flatten_grounding_values(args.get(field))
            if value
        ]
        if not values or any(value not in goal_l for value in values):
            return False
    return checked


def _provenance_options(tagger: ProvenanceTagger | None) -> dict:
    if tagger is None:
        return {}
    return {
        "reflection_watch_carveout": getattr(tagger, "reflection_watch_carveout", False),
    }


def run_fold_boundary(
    tagger: ProvenanceTagger,
    checker: CoherenceUnderFeatureShuffleChecker | None,
    *,
    user_goal: str,
    node_outputs: dict[str, str],
    accum: dict[str, Any] | None,
    boundary: str,
    current_text: str = "",
    proposed_tools: list[dict] | str | None = None,
    include_tool_output_shuffle: bool = True,
    allow_block: bool = True,
    allow_reflection_block: bool = True,
    reflection_probe: ReflectionProbe | None = None,
    process_text: str = "",
    reflection_watch_carveout: bool = False,
    goal_continuity: bool = True,
    per_tool_benign_pass: bool = False,
) -> ProvenancePipelineResult:
    """Reflect (primary sensor) → shuffle (structure) → tag → decide block."""
    accum = dict(accum or {})
    fs_results: list[tuple[str, FeatureShuffleResult]] = []
    reflection_result: ReflectionProbeResult | None = None
    escalation_carry_level = int(accum.get(PROVENANCE_CARRY_LEVEL_KEY, 0) or 0)

    ctx = context_from_node_outputs(
        user_goal,
        node_outputs,
        current_text=current_text,
        proposed_tools=proposed_tools if boundary == "tool_call" else None,
        node=boundary,
    )
    proc = (process_text or node_outputs.get("review", "")).strip()
    if proc:
        plan = node_outputs.get("plan", "").strip()
        if plan and not plan.lower().startswith("user_goal:") and plan not in proc:
            merged_proc = f"{plan}\n{proc}".strip()
        else:
            merged_proc = proc
        ctx = ProvenanceContext(
            user_goal=ctx.user_goal,
            review=merged_proc,
            tool_context=ctx.tool_context,
            proposed_tools_json=ctx.proposed_tools_json,
            node=boundary,
        )

    # 1. Reflection probe first — objective dot-mirror + feature slots 5–7
    prior_escalated = is_channel_escalated(accum)
    if reflection_probe is not None:
        reflection_result = reflection_probe.analyze_context(ctx, process_text=proc)

    escalated = is_channel_escalated(accum)

    # 2. Feature shuffle — structural coherence after reflection sensing
    if checker is not None:
        if boundary == "tool_call":
            fs = checker.check(ctx)
            fs_results.append(("tool_call", fs))
            if not fs.passed:
                accum = mark_feature_shuffle_drift(accum, reason=fs.reason)

        if include_tool_output_shuffle and (
            boundary == "tool_output"
            or (boundary == "tool_call" and _has_embedded_tool_result(current_text or node_outputs.get("tool_call", "")))
        ):
            prop_str = _proposed_tools_str(proposed_tools)
            if not prop_str and boundary == "tool_call":
                prop_str = node_outputs.get("tool_call", "")
            fs_ctx = _tool_output_context(
                user_goal,
                node_outputs,
                current_text=current_text or node_outputs.get("tool_call", ""),
                proposed_tools=prop_str,
            )
            fs = checker.check(fs_ctx)
            fs_results.append(("tool_output", fs))
            if not fs.passed:
                accum = mark_feature_shuffle_drift(accum, reason=fs.reason)

    # 3. Tagger — consumes reflection metrics as provenance features
    reflection_metrics = reflection_result.metrics if reflection_result else None
    prov_tag = tagger.tag_from_nodes(
        user_goal,
        node_outputs,
        current_text=current_text,
        proposed_tools=proposed_tools if boundary == "tool_call" else "",
        node=boundary,
        reflection_metrics=reflection_metrics,
    )
    accum = tagger.accumulate(accum, prov_tag, node=boundary, proposed_tools=proposed_tools)

    eff_sensitive = _effective_proposed_sensitive(proposed_tools)
    ipi_benign = is_ipi_benign_tool_eligible(accum)
    lexical_continuity = reflection_goal_continuous(
        reflection_result.metrics if reflection_result else None
    )
    goal_continuous, continuity_reason = _field_grounded_continuity(
        user_goal,
        node_outputs,
        proposed_tools,
        lexical_continuity=lexical_continuity,
    )
    current_drift = bool(
        prov_tag.block_recommended or prov_tag.drift_score >= tagger.block_threshold
    )
    drift_destination_conflict = (
        current_drift
        and any(
            isinstance(item, dict)
            and str(item.get("tool") or item.get("function") or "").lower()
            in _EXTERNAL_DESTINATION_TOOLS
            for item in (
                proposed_tools
                if isinstance(proposed_tools, list)
                else []
            )
        )
        and not _external_fields_grounded_in_goal(user_goal, proposed_tools)
    )
    continuity_softenable = (
        goal_continuity
        and goal_continuous
        and not accum.get(PROVENANCE_FEATURE_SHUFFLE_KEY)
    )
    misaligned_sensitive = (
        boundary == "tool_call"
        and eff_sensitive
        and (
            (
                reflection_watch_carveout
                and ipi_benign
                and not goal_continuous
            )
            or drift_destination_conflict
        )
    )
    if drift_destination_conflict:
        continuity_reason = "continuity_ungrounded_external_destination"

    if (
        reflection_result is not None
        and reflection_result.block_recommended
        and boundary == "tool_call"
        and (
            continuity_softenable
            or not eff_sensitive
            or (reflection_watch_carveout and ipi_benign)
        )
    ):
        pass_reason = (
            "reflection_goal_continuous_pass"
            if continuity_softenable
            else "reflection_benign_tool_pass"
        )
        reflection_result = ReflectionProbeResult(
            score=reflection_result.score,
            block_recommended=False,
            reason=pass_reason,
            metrics=reflection_result.metrics,
        )
        if continuity_softenable or not eff_sensitive:
            accum = soften_reflection_lockdown(accum, reason=pass_reason)

    if boundary == "tool_call" and not eff_sensitive and accum.get(PROVENANCE_REFLECTION_KEY):
        accum = soften_reflection_lockdown(accum, reason="read_tool_continuity")

    block, reason = (False, "")
    if allow_block:
        eff_sensitive = _effective_proposed_sensitive(proposed_tools)
        if (
            misaligned_sensitive
        ):
            block = True
            reason = continuity_reason
        elif (
            boundary == "tool_call"
            and prior_escalated
            and not continuity_softenable
            and exceeds_carry_ceiling(proposed_tools, carry_level=escalation_carry_level)
        ):
            sens = max_tool_sensitivity(proposed_tools)
            ceil = carry_sensitivity_ceiling(escalation_carry_level)
            block = True
            reason = f"channel_escalation:sens={sens:.2f}>ceiling={ceil:.2f}"
        elif (
            reflection_result is not None
            and reflection_result.block_recommended
            and allow_reflection_block
        ):
            accum = mark_reflection_drift(accum, reason=reflection_result.reason)
            block = True
            reason = reflection_result.reason
        else:
            if continuity_softenable and boundary == "tool_call":
                block, reason = (False, "goal_continuous_carry_pass")
            elif per_tool_benign_pass and not eff_sensitive:
                block, reason = (False, "")
            else:
                block, reason = tagger.should_block_boundary(
                    accum,
                    node=boundary,
                    current_score=prov_tag.drift_score,
                    proposed_sensitive=eff_sensitive if boundary == "tool_call" else None,
                    proposed_tools=proposed_tools if boundary == "tool_call" else None,
                    carry_tiered=getattr(tagger, "carry_tiered", True),
                )

    layer = ""
    if block:
        if reason.startswith("channel_escalation"):
            layer = "provenance"
        elif (
            reflection_result is not None
            and reflection_result.block_recommended
            and allow_reflection_block
        ):
            layer = "reflection"
        elif accum.get("_provenance_feature_shuffle"):
            layer = "feature_shuffle"
        else:
            layer = "provenance"
    elif continuity_softenable and boundary == "tool_call":
        accum = record_goal_aligned_boundary(accum)

    return ProvenancePipelineResult(
        accum=accum,
        prov_reason=prov_tag.reason,
        prov_score=prov_tag.drift_score,
        reflection_result=reflection_result,
        feature_shuffle_results=fs_results,
        block=block,
        block_reason=reason,
        block_layer=layer,
    )


run_provenance_boundary = run_fold_boundary
