"""Unified fold layer: schema/shuffle → provenance fold (single in/out)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bio_harness.elastic.controller import ElasticController
from bio_harness.fold.coherence_under_shuffle import CoherenceUnderShuffleChecker
from bio_harness.fold.pipeline import FoldPipeline
from bio_harness.provenance.feature_shuffle import CoherenceUnderFeatureShuffleChecker
from bio_harness.provenance.pipeline_check import run_provenance_boundary
from bio_harness.provenance.reflection_probe import ReflectionProbe, ReflectionProbeResult
from bio_harness.provenance.tagger import ProvenanceTagger

_DEFAULT_PROBE = object()


@dataclass
class FoldLayerResult:
    """Single entry/exit for fold + provenance sensing."""

    passed: bool
    reconstructed: str
    reason: str = ""
    accum: dict[str, Any] = field(default_factory=dict)
    block_layer: str = ""
    phase: str = ""  # schema | shuffle | provenance | none
    shuffle_rounds: int = 0
    prov_score: float = 0.0
    reflection_result: ReflectionProbeResult | None = None


class FoldLayer:
    """FoldLayer = conventional fold (schema/shuffle) + provenance fold (reflect/shuffle/tag)."""

    def __init__(
        self,
        *,
        schema_pipeline: FoldPipeline,
        tagger: ProvenanceTagger | None = None,
        reflection_probe: ReflectionProbe | None = None,
        feature_shuffle_checker: CoherenceUnderFeatureShuffleChecker | None = None,
        reflection_watch_carveout: bool = False,
        goal_continuity: bool = True,
    ) -> None:
        self._schema = schema_pipeline
        self._tagger = tagger
        self._reflection_probe = reflection_probe
        self._feature_shuffle_checker = feature_shuffle_checker
        self._reflection_watch_carveout = reflection_watch_carveout
        self._goal_continuity = goal_continuity

    def run(
        self,
        content: str,
        *,
        boundary: str,
        user_goal: str,
        node_outputs: dict[str, str] | None,
        accum: dict[str, Any] | None = None,
        session_id: str = "session",
        probe_count: int = 0,
        current_text: str = "",
        proposed_tools: list[dict] | str | None = None,
        current_node: str = "",
        include_tool_output_shuffle: bool = True,
        allow_block: bool = True,
        allow_reflection_block: bool = True,
        process_text: str = "",
        reflection_probe: ReflectionProbe | None | object = _DEFAULT_PROBE,
        per_tool_benign_pass: bool = False,
    ) -> FoldLayerResult:
        """Run full fold stack; return reconstructed text + carry accum + block state."""
        accum = dict(accum or {})
        node = current_node or boundary

        fold = self._schema.fold(
            content,
            session_id=session_id,
            probe_count=probe_count,
            user_goal=user_goal,
            current_node=node,
            node_outputs=node_outputs,
        )
        if not fold.passed:
            return FoldLayerResult(
                passed=False,
                reconstructed=fold.reconstructed,
                reason=fold.reason,
                accum=accum,
                phase=fold.phase or "schema",
                shuffle_rounds=fold.shuffle_rounds,
            )

        text = fold.reconstructed
        if self._tagger is None:
            return FoldLayerResult(
                passed=True,
                reconstructed=text,
                accum=accum,
                phase=fold.phase or "none",
                shuffle_rounds=fold.shuffle_rounds,
            )

        prov = run_provenance_boundary(
            self._tagger,
            self._feature_shuffle_checker,
            user_goal=user_goal,
            node_outputs=node_outputs or {},
            accum=accum,
            boundary=boundary,
            current_text=current_text or text,
            proposed_tools=proposed_tools,
            include_tool_output_shuffle=include_tool_output_shuffle,
            allow_block=allow_block,
            allow_reflection_block=allow_reflection_block,
            reflection_probe=(
                self._reflection_probe
                if reflection_probe is _DEFAULT_PROBE
                else reflection_probe
            ),
            process_text=process_text,
            reflection_watch_carveout=self._reflection_watch_carveout,
            goal_continuity=self._goal_continuity,
            per_tool_benign_pass=per_tool_benign_pass,
        )
        return FoldLayerResult(
            passed=not prov.block,
            reconstructed=text,
            reason=prov.block_reason or prov.prov_reason,
            accum=prov.accum,
            block_layer=prov.block_layer,
            phase="provenance",
            shuffle_rounds=fold.shuffle_rounds,
            prov_score=prov.prov_score,
            reflection_result=prov.reflection_result,
        )


def build_fold_layer(
    cfg,
    *,
    elastic: ElasticController | None = None,
    shuffle_checker: CoherenceUnderShuffleChecker | None = None,
    use_schema_fold: bool | None = None,
    use_shuffle_supplement: bool | None = None,
) -> FoldLayer:
    """Construct FoldLayer from harness config."""
    from bio_harness.provenance.feature_shuffle import make_feature_shuffle_checker
    from bio_harness.provenance.reflection_probe import get_reflection_probe
    from bio_harness.provenance.tagger import get_tagger

    schema = FoldPipeline(
        use_schema_fold=cfg.use_schema_fold if use_schema_fold is None else use_schema_fold,
        use_shuffle_supplement=cfg.use_shuffle_fold if use_shuffle_supplement is None else use_shuffle_supplement,
        elastic=elastic or ElasticController(
            default_rounds=cfg.default_shuffle_rounds,
            max_rounds=cfg.max_shuffle_rounds,
            enabled=cfg.use_elastic,
        ),
        shuffle_checker=shuffle_checker or CoherenceUnderShuffleChecker(
            use_llm_judge=getattr(cfg, "use_llm_shuffle_judge", False),
        ),
        default_rounds=cfg.default_shuffle_rounds,
    )
    from bio_harness.harness.continuity import resolve_continuity

    tagger = get_tagger(cfg)
    reflection = get_reflection_probe(cfg)
    continuity = resolve_continuity(cfg)
    if tagger is not None:
        tagger.ipi_light_state = continuity.ipi_light
    fs_checker = None
    if tagger is not None and cfg.use_feature_shuffle:
        fs_checker = make_feature_shuffle_checker(tagger.model, cfg)
    watch_carveout = continuity.reflection_continuity or getattr(
        cfg, "provenance_reflection_watch_carveout", False
    )
    return FoldLayer(
        schema_pipeline=schema,
        tagger=tagger,
        reflection_probe=reflection,
        feature_shuffle_checker=fs_checker,
        reflection_watch_carveout=watch_carveout,
        goal_continuity=bool(getattr(cfg, "provenance_goal_continuity", True)),
    )
