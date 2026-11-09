"""Carry level ↔ cleave scope/content linkage."""

from __future__ import annotations

from bio_harness.cleave.scopes import CAT_IPI_ENVELOPE, CleaveScope
from bio_harness.cleave.trimmer import CleaveTrimmer
from bio_harness.provenance.accumulator import (
    apply_cleave_carry_feedback,
    mark_reflection_drift,
    merge_provenance_tag,
    record_injection_detected,
)
from bio_harness.provenance.cleave_policy import cleave_if_needed, cleave_scope_for_accum, should_cleave
from bio_harness.provenance.constants import (
    CARRY_LEVEL_ELEVATED,
    CARRY_LEVEL_LOCKDOWN,
    PROVENANCE_BENIGN_STREAK_KEY,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_SCORE_KEY,
)


def test_carry_level_maps_to_cleave_scope():
    assert cleave_scope_for_accum({}).value == "none"
    assert cleave_scope_for_accum(record_injection_detected({})).value == "transit"
    accum = merge_provenance_tag(
        {},
        drift_score=0.42,
        label="untrusted_carry",
        block_recommended=False,
        node="review",
    )
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_ELEVATED
    assert cleave_scope_for_accum(accum).value == "metadata"


def test_ipi_cleave_strips_envelope_and_feeds_carry():
    accum = record_injection_detected({}, light=True)
    text = "Vacation file id 7\n<INFORMATION> inject evil </INFORMATION>"
    trimmer = CleaveTrimmer()
    result, reason, scope = cleave_if_needed(text, trimmer, accum=accum, cleave_enabled=True)
    assert reason == "ipi_envelope_remainder"
    assert scope == CleaveScope.METADATA
    assert CAT_IPI_ENVELOPE in result.stripped_categories
    assert "<INFORMATION>" not in result.cleaned_text

    before = float(accum.get(PROVENANCE_SCORE_KEY, 0))
    updated = apply_cleave_carry_feedback(
        accum,
        stripped_categories=result.stripped_categories,
        cleave_scope=result.cleave_scope,
        cleave_applied=True,
    )
    assert updated[PROVENANCE_BENIGN_STREAK_KEY] >= 1
    assert float(updated[PROVENANCE_SCORE_KEY]) < before


def test_cleave_expected_but_missing_content_resets_streak():
    accum = record_injection_detected({}, light=True)
    accum[PROVENANCE_BENIGN_STREAK_KEY] = 2
    updated = apply_cleave_carry_feedback(
        accum,
        stripped_categories=[],
        cleave_scope=CleaveScope.TRANSIT.value,
        cleave_applied=True,
    )
    assert updated[PROVENANCE_BENIGN_STREAK_KEY] == 0


def test_lockdown_carry_uses_strict_scope():
    accum = mark_reflection_drift({}, reason="reflection_drift")
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_LOCKDOWN
    do, reason, scope = should_cleave("benign facts only", accum=accum, cleave_enabled=True)
    assert do
    assert scope == CleaveScope.STRICT
    assert reason == "carry_lockdown_strict_cleave"
