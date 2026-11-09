"""Citation gate — harness-layer verification before trusted output."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bio_harness.citation.verify import (
    EntryVerification,
    StrictBibVerifier,
    extract_cite_keys,
    extract_inline_dois,
    parse_bib_text,
)


@dataclass
class CitationGateResult:
    passed: bool
    blocked_reason: str = ""
    cite_keys: list[str] = field(default_factory=list)
    inline_dois: list[str] = field(default_factory=list)
    entry_results: list[EntryVerification] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)


class CitationGate:
    """Verify draft text against a scoped production bib file only."""

    def __init__(
        self,
        bib_path: Path | None = None,
        *,
        allowed_bib_files: set[str] | None = None,
        fail_on_unknown_cite: bool = True,
        fail_on_inline_doi_mismatch: bool = True,
    ) -> None:
        self.bib_path = bib_path
        self.allowed_bib_files = allowed_bib_files or {"ref.bib"}
        self.fail_on_unknown_cite = fail_on_unknown_cite
        self.fail_on_inline_doi_mismatch = fail_on_inline_doi_mismatch
        self.verifier = StrictBibVerifier()

    def check(
        self,
        draft_text: str,
        *,
        bib_text: str | None = None,
        cited_keys: list[str] | None = None,
    ) -> CitationGateResult:
        cite_keys = cited_keys or extract_cite_keys(draft_text)
        inline_dois = extract_inline_dois(draft_text)

        if bib_text is None:
            if self.bib_path is None or not self.bib_path.exists():
                return CitationGateResult(
                    passed=False,
                    blocked_reason="missing_bib",
                    cite_keys=cite_keys,
                    inline_dois=inline_dois,
                )
            if self.bib_path.name not in self.allowed_bib_files:
                return CitationGateResult(
                    passed=False,
                    blocked_reason=f"bib_file_not_allowed:{self.bib_path.name}",
                    cite_keys=cite_keys,
                )
            bib_entries = self.verifier.verify_file(
                self.bib_path, allowed_files=self.allowed_bib_files
            )
            if not bib_entries.passed:
                return CitationGateResult(
                    passed=False,
                    blocked_reason="bib_file_verification_failed",
                    cite_keys=cite_keys,
                    entry_results=bib_entries.entries,
                )
            bib_map = parse_bib_text(
                self.bib_path.read_text(encoding="utf-8", errors="replace"),
                source_file=self.bib_path.name,
            )
        else:
            bib_map = parse_bib_text(bib_text, source_file="inline")
            report = self.verifier.verify_entries(bib_map)
            if not report.passed:
                return CitationGateResult(
                    passed=False,
                    blocked_reason="inline_bib_verification_failed",
                    cite_keys=cite_keys,
                    entry_results=report.entries,
                )

        unknown = [k for k in cite_keys if k not in bib_map]
        if unknown and self.fail_on_unknown_cite:
            return CitationGateResult(
                passed=False,
                blocked_reason=f"unknown_cite_keys:{','.join(unknown)}",
                cite_keys=cite_keys,
                unknown_keys=unknown,
            )

        cited_entries = {k: bib_map[k] for k in cite_keys if k in bib_map}
        report = self.verifier.verify_entries(cited_entries)
        if not report.passed:
            return CitationGateResult(
                passed=False,
                blocked_reason="cited_entry_verification_failed",
                cite_keys=cite_keys,
                entry_results=report.entries,
            )

        if inline_dois and self.fail_on_inline_doi_mismatch:
            bib_dois = {e.get("doi", "").lower() for e in bib_map.values() if e.get("doi")}
            for doi in inline_dois:
                if doi.lower() not in bib_dois:
                    return CitationGateResult(
                        passed=False,
                        blocked_reason=f"inline_doi_not_in_bib:{doi}",
                        cite_keys=cite_keys,
                        inline_dois=inline_dois,
                    )

        return CitationGateResult(
            passed=True,
            cite_keys=cite_keys,
            inline_dois=inline_dois,
            entry_results=report.entries,
        )
