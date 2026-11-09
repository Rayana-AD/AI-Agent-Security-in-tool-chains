"""AgentDojo IPI envelope handling — record-aware metadata cleave."""

from __future__ import annotations

import re

from bio_harness.cleave.scopes import CAT_IPI_ENVELOPE, INFO_ENVELOPE_RE

AGENTDOJO_INJECTION_BLOCK = INFO_ENVELOPE_RE
_CONTENT_FIELD_RE = re.compile(
    r"(?im)^(\s*content\s*:\s*)(?:\|[^\n]*\n(?:\s+[^\n]+\n)*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\n]+)"
)


def detect_injection_envelope(text: str) -> bool:
    return bool(AGENTDOJO_INJECTION_BLOCK.search(text))


def envelope_still_present(text: str) -> bool:
    return detect_injection_envelope(text)


def strip_injection_envelope(text: str) -> str:
    cleaned = AGENTDOJO_INJECTION_BLOCK.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def redact_content_fields(text: str) -> str:
    """Keep structural fields (id_, filename, owner); redact content bodies."""
    return _CONTENT_FIELD_RE.sub(r'\1"[redacted]"', text)


def _split_tool_records(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines:
        return [text]
    records: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("- ") and current:
            records.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        records.append(current)
    if len(records) <= 1:
        return [text]
    return ["\n".join(chunk) for chunk in records]


def _strip_record_metadata(record: str) -> str:
    if not detect_injection_envelope(record):
        return record
    out = strip_injection_envelope(record)
    if detect_injection_envelope(out):
        out = redact_content_fields(out)
    return out


def apply_metadata_strip(text: str) -> str:
    """Remove envelope per infected record; preserve benign records verbatim."""
    if not detect_injection_envelope(text):
        return text
    records = _split_tool_records(text)
    if len(records) == 1:
        return _strip_record_metadata(text)
    return "\n".join(_strip_record_metadata(rec) for rec in records)


def apply_agentdojo_metadata_cleave(text: str) -> tuple[str, list[str]]:
    """Cleave IPI envelope with AgentDojo record preservation; return cleaned + categories."""
    if not detect_injection_envelope(text):
        return text, []
    cleaned = apply_metadata_strip(text)
    if cleaned == text and not detect_injection_envelope(text):
        return cleaned, []
    return cleaned, [CAT_IPI_ENVELOPE]
