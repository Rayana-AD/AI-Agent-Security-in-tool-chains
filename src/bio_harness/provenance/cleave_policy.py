"""Situational cleave: signal-peptide trim only when fold layer says transport needs it."""

from __future__ import annotations

import re
from typing import Any

from bio_harness.cleave.scopes import (
    CAT_IPI_ENVELOPE,
    CAT_TRANSIT,
    CleaveScope,
    INFO_ENVELOPE_RE,
    strip_ipi_envelopes,
)
from bio_harness.cleave.trimmer import CleaveResult, CleaveTrimmer
from bio_harness.fold.chunker import ChunkType, SemanticChunker
from bio_harness.provenance.constants import (
    CARRY_LEVEL_ELEVATED,
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_WATCH,
    GATE_TAG_CONTROL,
    GATE_TAG_IPI_WATCH,
    GATE_TAG_REFLECTION,
    GATE_TAG_SHUFFLE,
    GATE_TAG_UNTRUSTED,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_GATE_TAG_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_REFLECTION_KEY,
)

TRANSIT_MARKERS = (
    "signal_peptide",
    "_routing_hint",
    "_gate_token",
    "routing_hint",
    "gate_token",
    "_validation_passed",
)


def cleave_scope_for_accum(accum: dict | None) -> CleaveScope:
    """Map fold carry state → how wide cleave should cut."""
    g = accum or {}
    level = int(g.get(PROVENANCE_CARRY_LEVEL_KEY, 0) or 0)
    gate_tag = str(g.get(PROVENANCE_GATE_TAG_KEY, "") or "")

    if (
        level >= CARRY_LEVEL_LOCKDOWN
        or g.get(PROVENANCE_REFLECTION_KEY)
        or g.get(PROVENANCE_FEATURE_SHUFFLE_KEY)
        or gate_tag in (GATE_TAG_REFLECTION, GATE_TAG_SHUFFLE, GATE_TAG_CONTROL)
    ):
        return CleaveScope.STRICT
    if level >= CARRY_LEVEL_ELEVATED or gate_tag == GATE_TAG_UNTRUSTED:
        return CleaveScope.METADATA
    if (
        level >= CARRY_LEVEL_WATCH
        or g.get(PROVENANCE_INJECTION_DETECTED_KEY)
        or gate_tag in (GATE_TAG_IPI_WATCH, GATE_TAG_UNTRUSTED)
    ):
        return CleaveScope.TRANSIT
    return CleaveScope.NONE


def _has_transit_signal(content: str) -> bool:
    tl = content.lower()
    if any(m in tl for m in TRANSIT_MARKERS):
        return True
    chunker = SemanticChunker()
    chunks = chunker.split(content)
    return any(c.chunk_type == ChunkType.ROUTE for c in chunks)


def should_cleave(
    content: str,
    *,
    accum: dict[str, Any] | None = None,
    cleave_enabled: bool = True,
) -> tuple[bool, str, CleaveScope]:
    """Return (do_cleave, reason, scope). Carry level sets scope; content triggers cut."""
    if not cleave_enabled:
        return False, "cleave_disabled", CleaveScope.NONE
    if not content.strip():
        return False, "empty_content", CleaveScope.NONE

    g = accum or {}
    scope = cleave_scope_for_accum(g)
    gate_tag = g.get(PROVENANCE_GATE_TAG_KEY, "")

    if scope == CleaveScope.STRICT:
        return True, "carry_lockdown_strict_cleave", scope

    if _has_transit_signal(content):
        return True, "transit_signal_present", scope

    if INFO_ENVELOPE_RE.search(content):
        return True, "ipi_envelope_remainder", scope

    if scope == CleaveScope.METADATA:
        tl = content.lower()
        if "routing-metadata" in tl or INFO_ENVELOPE_RE.search(content):
            return True, "elevated_metadata_cleave", scope
        chunker = SemanticChunker()
        if any(c.chunk_type == ChunkType.META for c in chunker.split(content)):
            return True, "elevated_meta_chunk_cleave", scope

    if scope == CleaveScope.TRANSIT:
        if g.get(PROVENANCE_INJECTION_DETECTED_KEY) or gate_tag == GATE_TAG_IPI_WATCH:
            if INFO_ENVELOPE_RE.search(content) or "routing-metadata" in content.lower():
                return True, "post_ipi_metadata_cleave", scope

    if gate_tag in (GATE_TAG_REFLECTION, GATE_TAG_SHUFFLE):
        if _has_transit_signal(content) or INFO_ENVELOPE_RE.search(content):
            return True, "fold_drift_transit_cleave", scope

    if scope == CleaveScope.NONE:
        return False, "no_cleave_signal", scope
    return False, "carry_scope_no_matching_content", scope


def cleave_if_needed(
    content: str,
    trimmer: CleaveTrimmer,
    *,
    accum: dict[str, Any] | None = None,
    cleave_enabled: bool = True,
) -> tuple[CleaveResult, str, CleaveScope]:
    """Apply cleave when carry state + content warrant it; scope follows carry level."""
    do_cleave, reason, scope = should_cleave(content, accum=accum, cleave_enabled=cleave_enabled)
    if not do_cleave:
        result = trimmer.cleave(content, enabled=False, scope=scope)
        return result, reason, scope
    result = trimmer.cleave(content, enabled=True, scope=scope)
    return result, reason, scope
