"""Feature-space shuffle coherence: permute node attributions to surface cross-node drift."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from bio_harness.provenance.classifier import ProvenanceModel, extract_model_features
from bio_harness.provenance.features import ProvenanceContext
from bio_harness.provenance.path_patterns import path_smuggle_signal


@dataclass
class FeatureShuffleResult:
    passed: bool
    score: float = 1.0
    reason: str = ""


def cross_node_inconsistent(
    goal: str,
    review: str,
    tool_context: str,
    proposed: str,
) -> str:
    """Rule-based cross-node inconsistency using generalized path patterns."""
    return path_smuggle_signal(goal, f"{review}\n{tool_context}", proposed)


class CoherenceUnderFeatureShuffleChecker:
    """Permute review / tool / proposed attributions; fail on instability or harm surfacing."""

    def __init__(
        self,
        model: ProvenanceModel,
        *,
        score_delta_threshold: float = 0.12,
        block_score_threshold: float = 0.18,
        use_hard_rules: bool = True,
    ) -> None:
        self.model = model
        self.score_delta_threshold = score_delta_threshold
        self.block_score_threshold = block_score_threshold
        self.use_hard_rules = use_hard_rules

    def check(self, ctx: ProvenanceContext) -> FeatureShuffleResult:
        if self.use_hard_rules:
            rule_reason = cross_node_inconsistent(
                ctx.user_goal,
                ctx.review,
                ctx.tool_context,
                ctx.proposed_tools_json,
            )
            if rule_reason:
                return FeatureShuffleResult(passed=False, score=0.15, reason=rule_reason)

        slots: list[tuple[str, str]] = []
        if ctx.review.strip():
            slots.append(("review", ctx.review))
        if ctx.tool_context.strip():
            slots.append(("tool_context", ctx.tool_context))
        if ctx.proposed_tools_json.strip():
            slots.append(("proposed", ctx.proposed_tools_json))

        if len(slots) < 2:
            return FeatureShuffleResult(passed=True)

        slot_names = [s[0] for s in slots]
        texts = [s[1] for s in slots]
        original_score = self.model.predict_proba(extract_model_features(ctx, self.model))
        scores = [original_score]

        for perm in set(permutations(texts)):
            if perm == tuple(texts):
                continue
            mapping = dict(zip(slot_names, perm))
            ctx_p = ProvenanceContext(
                user_goal=ctx.user_goal,
                review=mapping.get("review", ""),
                tool_context=mapping.get("tool_context", ""),
                proposed_tools_json=mapping.get("proposed", ""),
                node=ctx.node,
            )
            if self.use_hard_rules:
                perm_reason = cross_node_inconsistent(
                    ctx_p.user_goal,
                    ctx_p.review,
                    ctx_p.tool_context,
                    ctx_p.proposed_tools_json,
                )
                if perm_reason:
                    return FeatureShuffleResult(passed=False, score=0.2, reason=perm_reason)
            scores.append(self.model.predict_proba(extract_model_features(ctx_p, self.model)))

        score_range = max(scores) - min(scores)
        if score_range >= self.score_delta_threshold and max(scores) >= self.block_score_threshold:
            return FeatureShuffleResult(
                passed=False,
                score=1.0 - score_range,
                reason=f"feature_shuffle_score_delta:{score_range:.3f}",
            )

        return FeatureShuffleResult(passed=True, score=1.0 - score_range)


def make_feature_shuffle_checker(model: ProvenanceModel, config) -> CoherenceUnderFeatureShuffleChecker:
    return CoherenceUnderFeatureShuffleChecker(
        model,
        use_hard_rules=getattr(config, "feature_shuffle_hard_rules", True),
    )
