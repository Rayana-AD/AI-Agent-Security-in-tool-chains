"""Tests for strict citation verification and gate."""

from __future__ import annotations

from bio_harness.citation.gate import CitationGate
from bio_harness.citation.verify import (
    StrictBibVerifier,
    author_overlap,
    parse_bib_text,
    strict_title_match,
)
from eval.attacks.citation_hallucination import GAMA_META, build_samples


def test_strict_title_rejects_subset_only():
    bib = "Galaxy and Mass Assembly (GAMA)"
    api = "Galaxy and Mass Assembly (GAMA): survey diagnostics and core data release"
    result = strict_title_match(bib, api)
    assert result.status == "fail"
    assert "subset" in result.detail


def test_strict_title_accepts_exact():
    title = "Galaxy and Mass Assembly (GAMA): survey diagnostics and core data release"
    assert strict_title_match(title, title).status == "ok"


def test_author_overlap_required():
    bib = "Smith, J. and Jones, A."
    api = "Driver, S. P.; Liske, J.; Graham, A. W."
    assert author_overlap(bib, api).status == "fail"


def test_verifier_offline_fake_doi_fails():
    bib = """
@article{fake,
  title={Galaxy and Mass Assembly (GAMA): survey diagnostics and core data release},
  author={Driver, S. P.},
  year={2015},
  doi={10.1093/mnras/FAKE999}
}
"""
    entries = parse_bib_text(bib)
    verifier = StrictBibVerifier(
        metadata_overrides={
            "10.1093/mnras/FAKE999": {
                "title": "Unrelated Paper Title",
                "authors": "Driver, S. P.",
                "year": "2015",
                "doi": "10.1093/mnras/FAKE999",
            }
        }
    )
    report = verifier.verify_entries(entries)
    assert not report.passed


def test_citation_gate_blocks_unknown_key():
    sample = next(s for s in build_samples() if s["id"] == "cit_unknown_key_01")
    gate = CitationGate(allowed_bib_files={"ref.bib"})
    gate.verifier = StrictBibVerifier(metadata_overrides=sample["metadata_overrides"])
    result = gate.check(sample["scripted_outputs"]["draft"], bib_text=sample["bib_text"])
    assert not result.passed
    assert "unknown_cite" in result.blocked_reason


def test_citation_gate_blocks_audit_file():
    sample = next(s for s in build_samples() if s["id"] == "cit_audit_pollution_01")
    gate = CitationGate(allowed_bib_files={"ref.bib"})
    gate.verifier = StrictBibVerifier(metadata_overrides={"10.0000/fake.doi": {}})
    result = gate.check(
        sample["scripted_outputs"]["draft"],
        bib_text=sample["bib_text"],
    )
    assert not result.passed


def test_citation_gate_allows_benign():
    sample = next(s for s in build_samples() if s["id"] == "cit_benign_01")
    gate = CitationGate(allowed_bib_files={"ref.bib"})
    gate.verifier = StrictBibVerifier(metadata_overrides=sample["metadata_overrides"])
    result = gate.check(sample["scripted_outputs"]["draft"], bib_text=sample["bib_text"])
    assert result.passed
