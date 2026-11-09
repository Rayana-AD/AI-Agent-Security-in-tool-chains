"""Strict bibliography verification — fail-closed, no weak substring passes."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bio_harness.citation.cache import CitationCache

ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass
class FieldCheck:
    field: str
    status: str  # ok | fail | missing
    detail: str = ""


@dataclass
class EntryVerification:
    key: str
    passed: bool
    source: str = ""
    checks: list[FieldCheck] = field(default_factory=list)
    reason: str = ""


@dataclass
class VerificationReport:
    passed: bool
    entries: list[EntryVerification] = field(default_factory=list)
    fail_closed_errors: list[str] = field(default_factory=list)

    @property
    def failed_keys(self) -> list[str]:
        return [e.key for e in self.entries if not e.passed]


def normalize_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\\[a-zA-Z]+\{?", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\$[^$]*\$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strict_title_match(bib_title: str, api_title: str) -> FieldCheck:
    na, nb = normalize_text(bib_title), normalize_text(api_title)
    if not na or not nb:
        return FieldCheck("title", "fail", "empty title")
    if na == nb:
        return FieldCheck("title", "ok", "exact")
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / max(len(ta | tb), 1)
    # NO substring-only pass — fixes sky-map verify_bib_strict weakness
    if overlap >= 0.92:
        return FieldCheck("title", "ok", f"token_overlap={overlap:.2f}")
    if na in nb or nb in na:
        return FieldCheck("title", "fail", f"subset_only overlap={overlap:.2f}")
    return FieldCheck("title", "fail", f"overlap={overlap:.2f}")


def author_overlap(bib_author: str, api_authors: str) -> FieldCheck:
    def last_names(s: str) -> set[str]:
        names = re.split(r"\s+and\s+|;", s, flags=re.I)
        out: set[str] = set()
        for n in names:
            parts = [p.strip() for p in re.split(r",|\s+", n) if p.strip()]
            if parts:
                out.add(parts[0].lower() if "," in n else parts[-1].lower())
        return {x for x in out if len(x) > 1}

    ba, aa = last_names(bib_author), last_names(api_authors)
    if not ba:
        return FieldCheck("author", "missing", "no bib authors")
    if not aa:
        return FieldCheck("author", "fail", "no api authors")
    overlap = len(ba & aa) / len(ba)
    if overlap >= 0.5:
        return FieldCheck("author", "ok", f"last_name_overlap={overlap:.2f}")
    return FieldCheck("author", "fail", f"last_name_overlap={overlap:.2f}")


def parse_bib_text(text: str, *, source_file: str = "inline") -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"@\w+\{([^,]+),([\s\S]*?)\n\}", text):
        key = m.group(1).strip()
        body = m.group(2)
        entry: dict[str, str] = {"_file": source_file}
        for fm in re.finditer(
            r"(\w+)\s*=\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\"[^\"]*\")", body
        ):
            k, v = fm.group(1).lower(), fm.group(2).strip()
            if v.startswith("{"):
                v = v[1:-1]
            elif v.startswith('"'):
                v = v[1:-1]
            entry[k] = v
        entries[key] = entry
    return entries


def parse_bib_file(path: Path) -> dict[str, dict[str, str]]:
    return parse_bib_text(path.read_text(encoding="utf-8", errors="replace"), source_file=path.name)


class StrictBibVerifier:
    """Verify bib entries against arXiv/Crossref with fail-closed semantics."""

    def __init__(
        self,
        cache: CitationCache | None = None,
        metadata_overrides: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.cache = cache or CitationCache()
        self.metadata_overrides = metadata_overrides or {}

    def verify_file(
        self,
        path: Path,
        *,
        allowed_files: set[str] | None = None,
    ) -> VerificationReport:
        if allowed_files and path.name not in allowed_files:
            return VerificationReport(
                passed=False,
                fail_closed_errors=[f"file_not_allowed:{path.name}"],
            )
        entries = parse_bib_file(path)
        return self.verify_entries(entries)

    def verify_entries(self, entries: dict[str, dict[str, str]]) -> VerificationReport:
        results: list[EntryVerification] = []
        errors: list[str] = []
        for key, entry in entries.items():
            ev = self.verify_entry(key, entry)
            results.append(ev)
            if not ev.passed:
                errors.append(ev.reason or key)
        return VerificationReport(passed=all(r.passed for r in results), entries=results, fail_closed_errors=errors)

    def verify_entry(self, key: str, entry: dict[str, str]) -> EntryVerification:
        checks: list[FieldCheck] = []
        meta: dict[str, str] | None = None
        source = ""

        doi = entry.get("doi", "").strip()
        eprint = entry.get("eprint", "").strip()

        override_key = eprint or doi
        if override_key and override_key in self.metadata_overrides:
            meta = self.metadata_overrides[override_key]
            source = "override"
            if not meta:
                return EntryVerification(key=key, passed=False, source=source, reason="metadata_override_empty")
        elif eprint:
            source = "arxiv"
            meta, err = self._fetch_arxiv(eprint)
            if err:
                return EntryVerification(key=key, passed=False, source=source, reason=err)
        elif doi:
            source = "crossref"
            meta, err = self._fetch_crossref(doi)
            if err:
                return EntryVerification(key=key, passed=False, source=source, reason=err)
        else:
            return EntryVerification(key=key, passed=False, source="none", reason="missing_doi_and_eprint")

        if not meta:
            return EntryVerification(key=key, passed=False, source=source, reason="metadata_unavailable")

        if doi and meta.get("doi"):
            norm_bib = doi.lower().strip()
            norm_api = meta["doi"].lower().strip()
            if norm_bib != norm_api:
                checks.append(FieldCheck("doi", "fail", f"bib={norm_bib} api={norm_api}"))
            else:
                checks.append(FieldCheck("doi", "ok", "exact"))

        if entry.get("title") and meta.get("title"):
            checks.append(strict_title_match(entry["title"], meta["title"]))

        if entry.get("author") and meta.get("authors"):
            checks.append(author_overlap(entry["author"], meta["authors"]))

        if entry.get("year") and meta.get("year"):
            if str(entry["year"]).strip() != str(meta["year"]).strip():
                checks.append(FieldCheck("year", "fail", f"bib={entry['year']} api={meta['year']}"))
            else:
                checks.append(FieldCheck("year", "ok"))

        failed = [c for c in checks if c.status == "fail"]
        passed = len(failed) == 0 and any(c.status == "ok" for c in checks)
        reason = "; ".join(f"{c.field}:{c.detail}" for c in failed) if failed else ""
        return EntryVerification(key=key, passed=passed, source=source, checks=checks, reason=reason)

    def _fetch_arxiv(self, eprint: str) -> tuple[dict[str, str] | None, str]:
        eprint = eprint.split("v")[0]
        cached = self.cache.get("arxiv", eprint)
        if cached:
            return cached, ""
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"id_list": eprint, "max_results": 1}
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bio-harness-citation/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, f"arxiv_fetch_failed:{e}"
        root = ET.fromstring(xml)
        entry = root.find("a:entry", ARXIV_NS)
        if entry is None:
            return None, "arxiv_not_found"
        title = (entry.findtext("a:title", default="", namespaces=ARXIV_NS) or "").strip()
        published = entry.findtext("a:published", default="", namespaces=ARXIV_NS) or ""
        authors = []
        for author in entry.findall("a:author", ARXIV_NS):
            name = author.findtext("a:name", default="", namespaces=ARXIV_NS)
            if name:
                authors.append(name)
        doi_el = entry.find("arxiv:doi", ARXIV_NS)
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else ""
        payload = {
            "title": title,
            "year": published[:4] if published else "",
            "authors": "; ".join(authors[:8]),
            "doi": doi,
            "eprint": eprint,
        }
        self.cache.set("arxiv", eprint, payload)
        return payload, ""

    def _fetch_crossref(self, doi: str) -> tuple[dict[str, str] | None, str]:
        doi = doi.strip()
        cached = self.cache.get("crossref", doi)
        if cached:
            return cached, ""
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bio-harness-citation/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            return None, f"crossref_fetch_failed:{e}"
        msg = data.get("message", {})
        if not msg:
            return None, "crossref_empty"
        title_list = msg.get("title") or []
        title = title_list[0] if title_list else ""
        authors = []
        for a in msg.get("author") or []:
            family = a.get("family", "")
            given = a.get("given", "")
            if family:
                authors.append(f"{family}, {given}".strip(", "))
        payload = {
            "title": title,
            "year": str((msg.get("issued", {}).get("date-parts") or [[""]])[0][0]),
            "authors": "; ".join(authors[:8]),
            "doi": msg.get("DOI", doi),
        }
        self.cache.set("crossref", doi, payload)
        return payload, ""


def extract_cite_keys(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\\cite\{([^}]+)\}", text)))


def extract_inline_dois(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"10\.\d{4,9}/[^\s\]}\"']+", text)))
