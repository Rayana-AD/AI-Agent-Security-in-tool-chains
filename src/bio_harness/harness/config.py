"""Harness configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HarnessConfig:
    name: str = "full_bio_harness"
    use_schema_fold: bool = True
    use_shuffle_fold: bool = True  # shuffle supplement (after schema), not a replacement
    use_unidirectional_gate: bool = True
    use_state_partition: bool = True
    use_cleave: bool = True
    use_elastic: bool = True
    baseline: str | None = None
    max_retries: int = 3
    session_ttl_seconds: float = 600.0
    default_shuffle_rounds: int = 2
    max_shuffle_rounds: int = 5
    embedding_threshold: float = 0.75
    use_llm_judge: bool = False
    use_llm_shuffle_judge: bool = False
    use_citation_gate: bool = False
    citation_allowed_bib_files: tuple[str, ...] = ("ref.bib",)
    external_defense: str | None = None
    gate_nodes: tuple[str, ...] | None = None  # None = all nodes (plan, review, tool_call)
    use_provenance_tagger: bool = False
    provenance_model_path: str | None = None
    provenance_block_threshold: float | None = None  # None = use model threshold
    use_feature_shuffle: bool = False  # feature-space shuffle (Idea1 provenance supplement)
    use_cleave_release: bool = False  # strip injection then re-check instead of full withhold
    feature_shuffle_hard_rules: bool = True  # cross-node path/escalation hard rules
    # AgentDojo IPI timing at tool_output: withhold | escalate_pass | metadata_strip | withhold_guided
    agentdojo_ipi_output_mode: str = "withhold"
    cleave_release_veto_threshold: float | None = 0.45  # None = disable veto
    provenance_carry_decay_streak: int = 3
    provenance_carry_tiered: bool = True
    # Keep contamination state between boundaries within one episode.
    # Independent of use_carry_store, which only controls persistence.
    use_in_episode_carry: bool = True
    use_carry_store: bool = True
    carry_store_backend: str = "file"  # file | redis
    redis_url: str | None = None
    use_reflection_probe: bool = False
    reflection_block_threshold: float = 0.40
    reflection_dot_dim: int = 64
    # Saturation τ_α, τ_δ: auto loads .cache/reflection_scales.json (see eval/calibrate_reflection_scales.py)
    reflection_scale_mode: str = "auto"  # auto | fixed | calibrated
    reflection_scale_stat: str = "median"  # median | mean (used when (re)calibrating)
    reflection_scale_path: str | None = None
    reflection_tau_alpha: float | None = None
    reflection_tau_delta: float | None = None
    # When set (e.g. fold_gate_cleave), resolve_continuity() applies the meta_full runtime contract.
    continuity_orchestration: str | None = None
    provenance_reflection_watch_carveout: bool = False
    # Field-grounded Continuity softening. Drop-one sets this false.
    provenance_goal_continuity: bool = True
    provenance_ipi_light_state: bool = False
    provenance_per_tool_filter: bool = False
    provenance_task_fidelity_hint: bool = False
    # Optional engineering write budget Γ(c). The current Fold–Continuity path
    # keeps this off by default; historical profiles may enable it explicitly.
    carry_sens_ceiling: tuple[float, float, float, float] | None = None
    use_carry_sens_ceiling: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> HarnessConfig:
        model_cfg = d.get("model", {}).get("harness", {})
        consistency = d.get("model", {}).get("consistency", {})
        raw_gate_nodes = d.get("gate_nodes")
        gate_nodes = tuple(raw_gate_nodes) if raw_gate_nodes else None
        raw_ceiling = d.get("carry_sens_ceiling")
        ceiling: tuple[float, float, float, float] | None = None
        if raw_ceiling is not None:
            if not isinstance(raw_ceiling, (list, tuple)) or len(raw_ceiling) < 4:
                raise ValueError("carry_sens_ceiling must be a length-4 list")
            ceiling = tuple(float(raw_ceiling[i]) for i in range(4))  # type: ignore[assignment]
        return cls(
            name=d.get("name", "full"),
            use_schema_fold=d.get("use_schema_fold", True),
            use_shuffle_fold=d.get("use_shuffle_fold", True),
            use_unidirectional_gate=d.get("use_unidirectional_gate", True),
            use_state_partition=d.get("use_state_partition", True),
            use_cleave=d.get("use_cleave", True),
            use_elastic=d.get("use_elastic", True),
            baseline=d.get("baseline"),
            max_retries=model_cfg.get("max_retries", 3),
            session_ttl_seconds=model_cfg.get("session_ttl_seconds", 600),
            default_shuffle_rounds=model_cfg.get("default_shuffle_rounds", 2),
            max_shuffle_rounds=model_cfg.get("max_shuffle_rounds", 5),
            embedding_threshold=consistency.get("embedding_threshold", 0.75),
            use_llm_judge=d.get("use_llm_judge", False),
            use_llm_shuffle_judge=d.get("use_llm_shuffle_judge", False),
            use_citation_gate=d.get("use_citation_gate", False),
            citation_allowed_bib_files=tuple(d.get("citation_allowed_bib_files") or ("ref.bib",)),
            external_defense=d.get("external_defense"),
            gate_nodes=gate_nodes,
            use_provenance_tagger=d.get("use_provenance_tagger", False),
            provenance_model_path=d.get("provenance_model_path"),
            provenance_block_threshold=d.get("provenance_block_threshold"),
            use_feature_shuffle=d.get("use_feature_shuffle", False),
            use_cleave_release=d.get("use_cleave_release", False),
            feature_shuffle_hard_rules=d.get("feature_shuffle_hard_rules", True),
            agentdojo_ipi_output_mode=str(d.get("agentdojo_ipi_output_mode", "withhold")),
            cleave_release_veto_threshold=d.get("cleave_release_veto_threshold", 0.45),
            provenance_carry_decay_streak=int(d.get("provenance_carry_decay_streak", 3)),
            provenance_carry_tiered=d.get("provenance_carry_tiered", True),
            use_in_episode_carry=d.get("use_in_episode_carry", True),
            use_carry_store=d.get("use_carry_store", True),
            carry_store_backend=str(d.get("carry_store_backend", "file")),
            redis_url=d.get("redis_url"),
            use_reflection_probe=d.get("use_reflection_probe", False),
            reflection_block_threshold=float(d.get("reflection_block_threshold", 0.40)),
            reflection_dot_dim=int(d.get("reflection_dot_dim", 64)),
            reflection_scale_mode=str(d.get("reflection_scale_mode", "auto")),
            reflection_scale_stat=str(d.get("reflection_scale_stat", "median")),
            reflection_scale_path=d.get("reflection_scale_path"),
            reflection_tau_alpha=d.get("reflection_tau_alpha"),
            reflection_tau_delta=d.get("reflection_tau_delta"),
            continuity_orchestration=d.get("continuity_orchestration"),
            provenance_reflection_watch_carveout=d.get("provenance_reflection_watch_carveout", False),
            provenance_goal_continuity=d.get("provenance_goal_continuity", True),
            provenance_ipi_light_state=d.get("provenance_ipi_light_state", False),
            provenance_per_tool_filter=d.get("provenance_per_tool_filter", False),
            provenance_task_fidelity_hint=d.get("provenance_task_fidelity_hint", False),
            carry_sens_ceiling=ceiling,
            use_carry_sens_ceiling=d.get("use_carry_sens_ceiling", False),
        )
