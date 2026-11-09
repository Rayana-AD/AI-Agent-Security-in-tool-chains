"""Cross-node provenance features for lightweight drift classifier."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from bio_harness.provenance.constants import SENSITIVE_TOOLS
from bio_harness.provenance.path_patterns import is_sensitive_path, path_smuggle_signal, sensitive_paths_in

INFO_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")
TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")
TOOL_JSON_RE = re.compile(r'"tool"\s*:\s*"(\w+)"', re.I)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")


@dataclass
class ProvenanceContext:
    user_goal: str = ""
    review: str = ""
    tool_context: str = ""
    proposed_tools_json: str = ""
    node: str = "tool_call"


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text.lower())}


def _extract_tool_names(blob: str) -> set[str]:
    names: set[str] = set()
    for m in TOOL_JSON_RE.finditer(blob):
        names.add(m.group(1).lower())
    for m in re.finditer(r"(?im)^tool:\s*(\S+)", blob):
        names.add(m.group(1).lower())
    for m in re.finditer(r'"function"\s*:\s*"(\w+)"', blob):
        names.add(m.group(1).lower())
    return names


def _sensitive_tools_mentioned(text: str) -> set[str]:
    """Detect sensitive tool names in free text (not only structured tool JSON)."""
    tl = text.lower()
    return {name for name in SENSITIVE_TOOLS if name in tl}


def _entity_set(text: str) -> set[str]:
    ents: set[str] = set()
    for e in EMAIL_RE.findall(text):
        ents.add(e.lower())
    for ib in IBAN_RE.findall(text):
        ents.add(ib.lower())
    return ents


def feature_dim() -> int:
    """Fixed hand-crafted feature vector size (must match saved logistic models)."""
    return 24


def full_feature_dim(*, proj_dim: int = 32) -> int:
    from bio_harness.provenance.embedding import embedding_feature_dim

    return feature_dim() + embedding_feature_dim(proj_dim)


def extract_features(
    ctx: ProvenanceContext,
    *,
    reflection_metrics: Any | None = None,
) -> list[float]:
    """Structural features; slots 5–7 filled by reflection probe when available."""
    from bio_harness.provenance.reflection_probe import ReflectionMetrics, reflection_feature_slice

    if reflection_metrics is not None and not isinstance(reflection_metrics, ReflectionMetrics):
        reflection_metrics = None
    goal = ctx.user_goal or ""
    review = ctx.review or ""
    tool_ctx = ctx.tool_context or ""
    proposed = ctx.proposed_tools_json or ""
    combined_untrusted = f"{review}\n{tool_ctx}"
    goal_tok = _tokens(goal)
    untrusted_tok = _tokens(combined_untrusted)
    goal_tools = _tokens(" ".join(_extract_tool_names(goal)))
    prop_tools = _extract_tool_names(proposed)
    ctx_tools = _extract_tool_names(combined_untrusted)
    text_tools = _sensitive_tools_mentioned(combined_untrusted) | _sensitive_tools_mentioned(proposed)
    all_prop = prop_tools | ctx_tools | text_tools

    sensitive_prop = [t for t in all_prop if t in SENSITIVE_TOOLS]
    goal_entities = _entity_set(goal)
    untrusted_entities = _entity_set(combined_untrusted)
    prop_entities = _entity_set(proposed)
    novel_entities = untrusted_entities | prop_entities
    novel_not_in_goal = novel_entities - goal_entities

    overlap = len(goal_tok & untrusted_tok) / max(len(goal_tok | untrusted_tok), 1)
    tool_in_goal = (
        sum(1 for t in sensitive_prop if t in goal_tools or t in goal_tok) / max(len(sensitive_prop), 1)
        if sensitive_prop
        else 0.0
    )

    has_info = 1.0 if INFO_RE.search(combined_untrusted) else 0.0
    has_sensitive = 1.0 if sensitive_prop else 0.0
    entity_drift = 1.0 if novel_not_in_goal and sensitive_prop else 0.0
    sensitive_path_drift = 1.0 if path_smuggle_signal(goal, combined_untrusted, proposed) else 0.0
    has_sensitive_path = 1.0 if sensitive_paths_in(combined_untrusted) else 0.0

    # Slots 5–7: reflection probe (primary sensor); zeros when reflection disabled.
    reflection_slice = reflection_feature_slice(reflection_metrics)

    feats = [
        overlap,
        tool_in_goal,
        has_info,
        has_sensitive,
        entity_drift,
        *reflection_slice,
        len(sensitive_prop) / 5.0,
        len(novel_not_in_goal) / 5.0,
        min(len(goal) / 500.0, 1.0),
        min(len(combined_untrusted) / 2000.0, 1.0),
        1.0 if ctx.node == "tool_call" else 0.0,
        1.0 if ctx.node == "tool_output" else 0.0,
        1.0 if "send_money" in all_prop else 0.0,
        1.0 if "invite_user_to_slack" in all_prop else 0.0,
        1.0 if "send_email" in all_prop else 0.0,
        1.0 if "update_scheduled_transaction" in all_prop else 0.0,
        1.0 if "reserve_hotel" in all_prop else 0.0,
        1.0 if "post_webpage" in all_prop else 0.0,
        has_sensitive_path,
        1.0 if "ignore previous" in combined_untrusted.lower() else 0.0,
        sensitive_path_drift,
        float(len(prop_tools)),
    ]
    assert len(feats) == feature_dim()
    return feats


def extract_full_features(
    ctx: ProvenanceContext,
    *,
    backend,
    projector: np.ndarray,
    reflection_metrics: Any | None = None,
) -> list[float]:
    """Hand-crafted + frozen embedding features for MLP provenance model."""
    from bio_harness.provenance.embedding import embedding_pair_features

    hand = extract_features(ctx, reflection_metrics=reflection_metrics)
    goal = ctx.user_goal or ""
    untrusted = f"{ctx.review or ''}\n{ctx.tool_context or ''}".strip()
    proposed = ctx.proposed_tools_json or ""
    emb = embedding_pair_features(goal, untrusted, proposed, backend, projector)
    full = hand + emb
    return full


def context_from_node_outputs(
    user_goal: str,
    node_outputs: dict[str, str] | None,
    *,
    current_text: str = "",
    proposed_tools: list[dict] | str | None = None,
    node: str = "tool_call",
) -> ProvenanceContext:
    node_outputs = node_outputs or {}
    proposed_str = ""
    if proposed_tools is not None:
        if isinstance(proposed_tools, str):
            proposed_str = proposed_tools
        else:
            proposed_str = json.dumps(proposed_tools, ensure_ascii=False)
    plan = node_outputs.get("plan", "")
    review = node_outputs.get("review", "")
    merged_review = f"{plan}\n{review}".strip() if plan else review
    return ProvenanceContext(
        user_goal=user_goal,
        review=merged_review,
        tool_context=f"{node_outputs.get('tool_call', '')}\n{current_text}".strip(),
        proposed_tools_json=proposed_str,
        node=node,
    )
