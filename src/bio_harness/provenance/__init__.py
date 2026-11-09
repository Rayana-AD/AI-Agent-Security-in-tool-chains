"""Fold-layer provenance: reflection → shuffle → tag (replaces separate scoring stack).

In BioHarness architecture this module *is* the foldLayer for cross-node continuity:
objective dot-reflection sensing, structural feature-shuffle, discrete carry tags.
Cleave timing is decided upstream via ``cleave_policy`` (situational, not per-hop).
"""

from bio_harness.provenance.constants import (
    LABEL_CONTROL_DRIFT,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_SCORE_KEY,
)
from bio_harness.provenance.tagger import ProvenanceTag, ProvenanceTagger

__all__ = [
    "ProvenanceTagger",
    "ProvenanceTag",
    "PROVENANCE_DRIFT_KEY",
    "PROVENANCE_SCORE_KEY",
    "LABEL_CONTROL_DRIFT",
]
