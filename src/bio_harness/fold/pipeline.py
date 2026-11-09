"""Fold pipeline: schema (conventional) → shuffle supplement → coherence probe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bio_harness.elastic.controller import ElasticController
from bio_harness.fold.chunker import SemanticChunker
from bio_harness.fold.coherence_under_shuffle import CoherenceUnderShuffleChecker
from bio_harness.fold.shuffle import controlled_shuffle


@dataclass
class FoldResult:
    passed: bool
    reconstructed: str
    reason: str = ""
    shuffle_rounds: int = 0
    consistency_score: float = 0.0
    phase: str = ""  # schema | shuffle | none


_NODE_ORDER = ("plan", "review", "tool_call")


class FoldPipeline:
    def __init__(
        self,
        *,
        use_schema_fold: bool = True,
        use_shuffle_supplement: bool = False,
        elastic: ElasticController | None = None,
        shuffle_checker: CoherenceUnderShuffleChecker | None = None,
        default_rounds: int = 2,
    ) -> None:
        self.use_schema_fold = use_schema_fold
        self.use_shuffle_supplement = use_shuffle_supplement
        self.elastic = elastic or ElasticController()
        self.shuffle_checker = shuffle_checker or CoherenceUnderShuffleChecker()
        self.chunker = SemanticChunker()
        self.default_rounds = default_rounds

    def fold(
        self,
        output: str | dict[str, Any],
        *,
        session_id: str,
        probe_count: int = 0,
        node_outputs: dict[str, str | dict[str, Any]] | None = None,
        user_goal: str = "",
        current_node: str = "",
    ) -> FoldResult:
        if isinstance(output, dict):
            original_text = self.chunker.reconstruct(self.chunker.split(output))
        else:
            original_text = str(output)

        # Phase 1 — conventional schema fold (always first when enabled)
        if self.use_schema_fold:
            schema_result = self._static_schema_fold(output, original_text)
            if not schema_result.passed:
                schema_result.phase = "schema"
                return schema_result
            working_text = schema_result.reconstructed
        else:
            working_text = original_text

        if not self.use_shuffle_supplement:
            return FoldResult(
                passed=True,
                reconstructed=working_text,
                phase="schema" if self.use_schema_fold else "none",
            )

        # Phase 2 — shuffle supplement on accumulated context (cross-node rational lies)
        supplement_source = self._merge_node_outputs(node_outputs) if node_outputs else working_text
        if not supplement_source.strip():
            supplement_source = working_text

        return self._shuffle_supplement(
            original=supplement_source,
            session_id=session_id,
            probe_count=probe_count,
            fallback_text=working_text,
            user_goal=user_goal,
            allow_llm_judge=current_node == "tool_call",
        )

    def fold_merged(
        self,
        node_outputs: dict[str, str | dict[str, Any]],
        *,
        session_id: str,
        probe_count: int = 0,
        node_order: tuple[str, ...] = _NODE_ORDER,
        user_goal: str = "",
    ) -> FoldResult:
        """Merge multi-node outputs; schema on latest node, shuffle on full context."""
        latest_node = node_order[-1]
        for n in reversed(node_order):
            if n in node_outputs and node_outputs[n]:
                latest_node = n
                break
        latest = node_outputs.get(latest_node, "")
        return self.fold(
            latest,
            session_id=session_id,
            probe_count=probe_count,
            node_outputs=node_outputs,
            user_goal=user_goal,
            current_node=latest_node,
        )

    def _merge_node_outputs(self, node_outputs: dict[str, str | dict[str, Any]]) -> str:
        parts: list[str] = []
        for node in _NODE_ORDER:
            raw = node_outputs.get(node)
            if not raw:
                continue
            if isinstance(raw, dict):
                text = self.chunker.reconstruct(self.chunker.split(raw))
            else:
                text = str(raw).strip()
            if text:
                parts.append(f"[{node}]\n{text}")
        return "\n\n".join(parts)

    def _shuffle_supplement(
        self,
        *,
        original: str,
        session_id: str,
        probe_count: int,
        fallback_text: str,
        user_goal: str = "",
        allow_llm_judge: bool = False,
    ) -> FoldResult:
        chunks = self.chunker.split(original)
        if len(chunks) < 2:
            return FoldResult(
                passed=True,
                reconstructed=fallback_text,
                phase="shuffle",
                reason="shuffle_skipped_single_chunk",
            )

        rounds = self.elastic.shuffle_rounds(probe_count)
        shuffled = controlled_shuffle(chunks, session_id=session_id, rounds=rounds)
        reconstructed = self.chunker.reconstruct(shuffled.chunks)
        check = self.shuffle_checker.check(
            original, reconstructed, user_goal=user_goal, allow_llm_judge=allow_llm_judge
        )

        if not check.passed:
            return FoldResult(
                passed=False,
                reconstructed=reconstructed,
                reason=check.reason,
                shuffle_rounds=rounds,
                consistency_score=check.score,
                phase="shuffle",
            )

        return FoldResult(
            passed=True,
            reconstructed=fallback_text,
            shuffle_rounds=rounds,
            consistency_score=check.score,
            phase="shuffle",
        )

    def _static_schema_fold(self, output: str | dict[str, Any], original_text: str) -> FoldResult:
        try:
            if isinstance(output, dict):
                required = {"plan", "action"}
                if not required.intersection(output.keys()):
                    return FoldResult(passed=False, reconstructed=original_text, reason="schema_missing_fields")
            else:
                import json

                text = output.strip()
                if text.startswith("{"):
                    data = json.loads(text)
                else:
                    data = {"raw": text}
                if "plan" not in data and "action" not in data:
                    tl = text.lower()
                    allowed_markers = ("plan:", "tool:", "action:", "approved", "review:", "safe")
                    if not any(m in tl for m in allowed_markers):
                        return FoldResult(
                            passed=False,
                            reconstructed=original_text,
                            reason="schema_missing_fields",
                        )
        except Exception as e:
            return FoldResult(passed=False, reconstructed=original_text, reason=f"schema_parse_error:{e}")
        return FoldResult(passed=True, reconstructed=original_text, shuffle_rounds=0)
