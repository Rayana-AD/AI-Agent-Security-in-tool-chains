"""bio_04-aligned configs for reviewer-facing ablation experiments.

Main paper AgentDojo results use defense ``bio_04`` → ``idea1_provenance_mlp_bio_04``
with ``continuity_orchestration: fold_gate_cleave``. Supplementary audits must use the
same profile (not legacy ``idea1_provenance_mlp`` or explicit-only meta_full flags).
"""

from __future__ import annotations

from dataclasses import asdict

from bio_harness.config import get_harness_config
from bio_harness.harness.config import HarnessConfig
from bio_harness.harness.continuity import resolve_continuity

# Primary live / paper config
BIO04_CONFIG = "idea1_provenance_mlp_bio_04"

# Scripted provenance generalization pair (full bio_04 vs hard-rules off)
BIO04_GENERALIZATION_PAIR = (
    BIO04_CONFIG,
    "bio_04_no_hard_rules",
)

# Integration ablation pair (full vs reflection removed, same continuity stack)
BIO04_INTEGRATION_PAIR = (
    BIO04_CONFIG,
    "bio_04_minus_reflection",
)

# Live AgentDojo drop-one defenses (full uses same runtime as bio_04)
LIVE_DROPONE_DEFENSES = (
    "bio_04",
    "bio_04_minus_reflection",
    "bio_04_minus_feature_shuffle",
    "bio_04_minus_hard_rules",
    "bio_04_minus_goal_continuity",
    "bio_04_minus_metadata_repair",
)

# Map defense keys used in AgentDojo to harness config keys
LIVE_DROPONE_CONFIG_KEYS = {
    "bio_04": BIO04_CONFIG,
    "bio_04_explicit_full": "bio_04_explicit_full",
    "bio_04_minus_reflection": "bio_04_minus_reflection",
    "bio_04_minus_feature_shuffle": "bio_04_minus_feature_shuffle",
    "bio_04_minus_hard_rules": "bio_04_minus_hard_rules",
    "bio_04_minus_goal_continuity": "bio_04_minus_goal_continuity",
    "bio_04_minus_metadata_repair": "bio_04_minus_metadata_repair",
}


def harness_config(key: str) -> HarnessConfig:
    return HarnessConfig.from_dict(get_harness_config(key))


def continuity_snapshot(key: str) -> dict:
    cfg = harness_config(key)
    profile = resolve_continuity(cfg)
    return {
        "config_key": key,
        "continuity_orchestration": cfg.continuity_orchestration,
        "use_reflection_probe": cfg.use_reflection_probe,
        "use_feature_shuffle": cfg.use_feature_shuffle,
        "feature_shuffle_hard_rules": cfg.feature_shuffle_hard_rules,
        "use_shuffle_fold": cfg.use_shuffle_fold,
        "profile": asdict(profile),
    }


def audit_alignment() -> dict:
    """Verify reviewer ablation configs resolve to intended continuity profiles."""
    base = continuity_snapshot(BIO04_CONFIG)
    explicit = continuity_snapshot("bio_04_explicit_full")
    notes: list[str] = []
    if base["profile"] != explicit["profile"]:
        notes.append("bio_04_explicit_full profile differs from idea1_provenance_mlp_bio_04")

    goal = continuity_snapshot("bio_04_minus_goal_continuity")
    if goal["profile"]["reflection_continuity"]:
        notes.append("bio_04_minus_goal_continuity still has reflection_continuity=True")

    meta = continuity_snapshot("bio_04_minus_metadata_repair")
    if meta["profile"]["ipi_output_mode"] != "withhold":
        notes.append("bio_04_minus_metadata_repair ipi_output_mode is not withhold")

    hard = continuity_snapshot("bio_04_no_hard_rules")
    if hard["feature_shuffle_hard_rules"]:
        notes.append("bio_04_no_hard_rules still has hard rules enabled")

    return {
        "bio_04_base": base,
        "bio_04_explicit_full": explicit,
        "bio_04_minus_goal_continuity": goal,
        "bio_04_minus_metadata_repair": meta,
        "bio_04_no_hard_rules": hard,
        "aligned": not notes,
        "notes": notes,
    }
