"""Cleave scope tiers and content stripping helpers."""

from __future__ import annotations

import re
from enum import Enum

from bio_harness.fold.chunker import ChunkType, SemanticChunk

INFO_ENVELOPE_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")

CAT_IPI_ENVELOPE = "ipi_envelope"
CAT_TRANSIT = "transit"
CAT_METADATA = "metadata"
CAT_STRICT = "strict_trim"


class CleaveScope(str, Enum):
    NONE = "none"
    TRANSIT = "transit"  # WATCH: signal-peptide / IPI envelope
    METADATA = "metadata"  # ELEVATED: + meta / routing-metadata lines
    STRICT = "strict"  # LOCKDOWN: aggressive trim of suspicious non-param lines


def strip_ipi_envelopes(text: str) -> tuple[str, list[str]]:
    stripped: list[str] = []

    def _repl(_match: re.Match[str]) -> str:
        stripped.append(CAT_IPI_ENVELOPE)
        return ""

    cleaned = INFO_ENVELOPE_RE.sub(_repl, text)
    return cleaned.strip(), stripped


def chunk_stripped_by_scope(chunk: SemanticChunk, scope: CleaveScope) -> str | None:
    """Return strip category if chunk should be removed at scope, else None."""
    if scope == CleaveScope.NONE:
        return None
    if chunk.chunk_type == ChunkType.ROUTE:
        return CAT_TRANSIT
    if scope in (CleaveScope.METADATA, CleaveScope.STRICT) and chunk.chunk_type == ChunkType.META:
        return CAT_METADATA
    if scope == CleaveScope.STRICT:
        tl = chunk.text.lower()
        if "routing-metadata" in tl or "ignore previous" in tl or "override" in tl:
            return CAT_STRICT
    return None
