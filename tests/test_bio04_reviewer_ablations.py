"""Tests for bio_04 reviewer ablation config alignment."""

from __future__ import annotations

from eval.bio04_reviewer_ablations import (
    BIO04_CONFIG,
    BIO04_GENERALIZATION_PAIR,
    LIVE_DROPONE_DEFENSES,
    audit_alignment,
    continuity_snapshot,
)


def test_bio04_explicit_full_matches_base_profile():
    base = continuity_snapshot(BIO04_CONFIG)
    explicit = continuity_snapshot("bio_04_explicit_full")
    assert base["profile"] == explicit["profile"]


def test_bio04_minus_goal_disables_reflection_continuity():
    goal = continuity_snapshot("bio_04_minus_goal_continuity")
    assert goal["profile"]["reflection_continuity"] is False
    assert goal["profile"]["ipi_output_mode"] == "metadata_strip"


def test_bio04_minus_metadata_uses_withhold():
    meta = continuity_snapshot("bio_04_minus_metadata_repair")
    assert meta["profile"]["ipi_output_mode"] == "withhold"


def test_bio04_no_hard_rules_flag():
    hard = continuity_snapshot("bio_04_no_hard_rules")
    assert hard["feature_shuffle_hard_rules"] is False
    assert hard["profile"] == continuity_snapshot(BIO04_CONFIG)["profile"]


def test_audit_alignment_passes():
    report = audit_alignment()
    assert report["aligned"], report["notes"]


def test_generalization_pair_uses_bio04():
    assert BIO04_GENERALIZATION_PAIR[0] == BIO04_CONFIG
    assert "bio_04" in BIO04_GENERALIZATION_PAIR[1]


def test_live_dropone_includes_bio04():
    assert LIVE_DROPONE_DEFENSES[0] == "bio_04"
