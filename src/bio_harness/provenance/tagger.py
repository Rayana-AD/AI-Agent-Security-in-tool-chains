"""Provenance tagger: cross-node drift score → Idea1-consumable labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bio_harness.provenance.accumulator import merge_provenance_tag, should_block_at_boundary
from bio_harness.provenance.classifier import ProvenanceModel, extract_model_features, rule_bootstrap_mlp, rule_bootstrap_weights
from bio_harness.provenance.constants import (
    GATE_TAG_CONTROL,
    GATE_TAG_REFLECTION,
    GATE_TAG_SHUFFLE,
    GATE_TAG_UNTRUSTED,
    LABEL_CONTROL_DRIFT,
    LABEL_UNTRUSTED_CARRY,
    PROVENANCE_CARRY_THRESHOLD,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_GATE_TAG_KEY,
    PROVENANCE_LABEL_KEY,
    PROVENANCE_SCORE_KEY,
)
from bio_harness.provenance.features import ProvenanceContext, context_from_node_outputs, extract_features
from bio_harness.provenance.reflection_probe import ReflectionMetrics

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "provenance_tagger_v1.json"


@dataclass
class ProvenanceTag:
    drift_score: float
    label: str
    block_recommended: bool
    reason: str

    def to_pollution(self) -> dict:
        return {
            PROVENANCE_SCORE_KEY: self.drift_score,
            PROVENANCE_LABEL_KEY: self.label,
            PROVENANCE_DRIFT_KEY: self.block_recommended,
        }


class ProvenanceTagger:
    def __init__(
        self,
        model: ProvenanceModel | None = None,
        *,
        model_path: str | Path | None = None,
        block_threshold: float | None = None,
        carry_tiered: bool = True,
    ) -> None:
        if model is not None:
            self.model = model
        elif model_path and Path(model_path).exists():
            self.model = ProvenanceModel.load(model_path)
        elif DEFAULT_MODEL_PATH.exists():
            self.model = ProvenanceModel.load(DEFAULT_MODEL_PATH)
        else:
            self.model = rule_bootstrap_weights()
        self.block_threshold = block_threshold if block_threshold is not None else self.model.threshold
        self.carry_tiered = carry_tiered

    def tag(
        self,
        ctx: ProvenanceContext,
        *,
        reflection_metrics: ReflectionMetrics | None = None,
    ) -> ProvenanceTag:
        feats = extract_model_features(ctx, self.model, reflection_metrics=reflection_metrics)
        hand = extract_features(ctx, reflection_metrics=reflection_metrics)
        score = self.model.predict_proba(feats)
        drift = self.model.predict_drift(feats) and ctx.node in ("tool_call", "tool_output")

        # Structural: sensitive action proposed in untrusted channel with novel entities.
        if (
            not drift
            and ctx.node in ("tool_call", "tool_output")
            and hand[3] >= 1.0
            and hand[4] >= 1.0
        ):
            drift = True
            score = max(score, self.block_threshold)

        if drift:
            label = LABEL_CONTROL_DRIFT
            reason = f"provenance_drift:score={score:.3f}"
        elif score >= PROVENANCE_CARRY_THRESHOLD:
            label = LABEL_UNTRUSTED_CARRY
            reason = f"provenance_untrusted_carry:score={score:.3f}"
            drift = False
        else:
            label = "provenance_aligned"
            reason = f"provenance_aligned:score={score:.3f}"

        return ProvenanceTag(
            drift_score=score,
            label=label,
            block_recommended=drift,
            reason=reason,
        )

    def tag_from_nodes(
        self,
        user_goal: str,
        node_outputs: dict[str, str] | None,
        *,
        current_text: str = "",
        proposed_tools: list[dict] | str | None = None,
        node: str = "tool_call",
        reflection_metrics: ReflectionMetrics | None = None,
    ) -> ProvenanceTag:
        ctx = context_from_node_outputs(
            user_goal,
            node_outputs,
            current_text=current_text,
            proposed_tools=proposed_tools,
            node=node,
        )
        return self.tag(ctx, reflection_metrics=reflection_metrics)

    def accumulate(
        self,
        global_store: dict[str, Any] | None,
        tag: ProvenanceTag,
        *,
        node: str,
        proposed_tools: list[dict] | str | None = None,
    ) -> dict[str, Any]:
        return merge_provenance_tag(
            global_store,
            drift_score=tag.drift_score,
            label=tag.label,
            block_recommended=tag.block_recommended,
            node=node,
            proposed_tools=proposed_tools,
        )

    def should_block_boundary(
        self,
        global_store: dict[str, Any] | None,
        *,
        node: str,
        current_score: float | None = None,
        proposed_sensitive: bool | None = None,
        proposed_tools: list[dict] | str | None = None,
        carry_tiered: bool = True,
    ) -> tuple[bool, str]:
        return should_block_at_boundary(
            global_store,
            node=node,
            threshold=self.block_threshold,
            current_score=current_score,
            proposed_sensitive=proposed_sensitive,
            proposed_tools=proposed_tools,
            carry_tiered=carry_tiered,
        )

    def apply_to_state(self, state, tag: ProvenanceTag, *, node: str = "tool_call") -> dict[str, Any]:
        """Write cumulative provenance tags into partition global store."""
        current = getattr(state, "_global", {})
        merged = self.accumulate(current, tag, node=node)
        for k, v in merged.items():
            if k.startswith("_provenance") or k in (
                PROVENANCE_SCORE_KEY,
                PROVENANCE_LABEL_KEY,
                PROVENANCE_DRIFT_KEY,
            ):
                state.merge_global_pollution(k, v)
        return merged


def get_tagger(config) -> ProvenanceTagger | None:
    if not getattr(config, "use_provenance_tagger", False):
        return None
    path = getattr(config, "provenance_model_path", None) or DEFAULT_MODEL_PATH
    block_threshold = getattr(config, "provenance_block_threshold", None)
    carry_tiered = getattr(config, "provenance_carry_tiered", True)
    tagger = ProvenanceTagger(model_path=path, block_threshold=block_threshold, carry_tiered=carry_tiered)
    tagger.reflection_watch_carveout = getattr(config, "provenance_reflection_watch_carveout", False)
    tagger.ipi_light_state = getattr(config, "provenance_ipi_light_state", False)
    tagger.per_tool_filter = getattr(config, "provenance_per_tool_filter", False)
    return tagger
