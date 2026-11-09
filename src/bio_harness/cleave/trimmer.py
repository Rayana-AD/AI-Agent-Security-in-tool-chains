"""Signal-peptide style field trimming after gate pass."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bio_harness.cleave.scopes import (
    CAT_IPI_ENVELOPE,
    CleaveScope,
    chunk_stripped_by_scope,
    strip_ipi_envelopes,
)
from bio_harness.fold.chunker import ChunkType, SemanticChunk, SemanticChunker, TRANSIT_FIELD_PREFIXES


TRANSIT_ONLY_KEYS = {
    "_routing_hint",
    "_gate_token",
    "_validation_passed",
    "signal_peptide",
    "routing_hint",
    "gate_token",
    "validation_passed",
}


@dataclass
class CleaveResult:
    cleaned_text: str
    cleaned_dict: dict[str, Any]
    stripped_fields: list[str]
    facts: list[str]
    tool_calls: list[dict[str, Any]]
    plans: list[str]
    stripped_categories: list[str] = field(default_factory=list)
    cleave_scope: str = CleaveScope.NONE.value


class CleaveTrimmer:
    ROUTE_LINE = re.compile(
        r"(?i)^.*?(signal_peptide|_gate_token|_routing_hint|_validation_passed|routing_hint)\s*[:=].*$"
    )

    def __init__(self) -> None:
        self.chunker = SemanticChunker()

    def cleave(
        self,
        content: str | dict[str, Any],
        *,
        enabled: bool = True,
        scope: CleaveScope | str = CleaveScope.TRANSIT,
    ) -> CleaveResult:
        scope_enum = CleaveScope(scope) if isinstance(scope, str) else scope
        if isinstance(content, dict):
            return self._cleave_dict(content, enabled=enabled, scope=scope_enum)
        return self._cleave_text(str(content), enabled=enabled, scope=scope_enum)

    def _cleave_dict(self, data: dict[str, Any], *, enabled: bool, scope: CleaveScope) -> CleaveResult:
        stripped: list[str] = []
        categories: list[str] = []
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if enabled and scope != CleaveScope.NONE and (k in TRANSIT_ONLY_KEYS or k.startswith("_")):
                stripped.append(k)
                categories.append("transit")
                continue
            cleaned[k] = v
        text = self.chunker.reconstruct(self.chunker.split(cleaned))
        return CleaveResult(
            cleaned_text=text,
            cleaned_dict=cleaned,
            stripped_fields=stripped,
            stripped_categories=categories,
            cleave_scope=scope.value,
            facts=_extract_facts(cleaned),
            tool_calls=_extract_tool_calls(cleaned),
            plans=_extract_plans(cleaned),
        )

    def _cleave_text(self, text: str, *, enabled: bool, scope: CleaveScope) -> CleaveResult:
        categories: list[str] = []
        working = text
        if enabled and scope != CleaveScope.NONE:
            working, ipi_cats = strip_ipi_envelopes(working)
            categories.extend(ipi_cats)

        chunks = self.chunker.split(working)
        if not enabled or scope == CleaveScope.NONE:
            cleaned_chunks = chunks
            stripped = []
        else:
            cleaned_chunks = []
            stripped = []
            for c in chunks:
                cat = chunk_stripped_by_scope(c, scope)
                if cat:
                    stripped.append(c.source_key or c.text[:40])
                    categories.append(cat)
                    continue
                if _is_transit_line(c.text) and scope != CleaveScope.NONE:
                    stripped.append(c.source_key or c.text[:40])
                    categories.append("transit")
                    continue
                cleaned_chunks.append(c)

        cleaned_text = self.chunker.reconstruct(cleaned_chunks)
        cleaned_dict = self.chunker.reconstruct_dict(cleaned_chunks)
        tool_calls = _extract_tool_calls(cleaned_dict)
        if not tool_calls:
            tool_calls = _extract_tool_calls_from_text(cleaned_text)
        return CleaveResult(
            cleaned_text=cleaned_text,
            cleaned_dict=cleaned_dict,
            stripped_fields=stripped,
            stripped_categories=categories,
            cleave_scope=scope.value,
            facts=_extract_facts_from_chunks(cleaned_chunks),
            tool_calls=tool_calls,
            plans=_extract_plans(cleaned_dict),
        )


def _is_transit_line(line: str) -> bool:
    ll = line.strip().lower()
    if ll.startswith("_") or "signal_peptide" in ll or "routing_hint" in ll or "gate_token" in ll:
        return True
    return any(ll.startswith(p) for p in ("validation_passed", "_validation"))


def _extract_facts(data: dict[str, Any]) -> list[str]:
    facts = []
    for k, v in data.items():
        if k in ("plan", "summary", "fact", "observation"):
            facts.append(str(v))
    return facts


def _extract_facts_from_chunks(chunks: list[SemanticChunk]) -> list[str]:
    return [c.text for c in chunks if c.chunk_type == ChunkType.FACT]


def _extract_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "tool" in data or "tool_name" in data:
        return [{"tool": data.get("tool") or data.get("tool_name"), "args": data.get("args") or data.get("parameters", {})}]
    if "action" in data:
        return [{"tool": data["action"], "args": data.get("parameters", {})}]
    return []


def _extract_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    import json
    import re

    tool_match = re.search(r"(?im)^tool:\s*(\S+)", text)
    args_match = re.search(r"(?im)^args:\s*(\{.*\})", text)
    if not tool_match:
        return []
    args: dict[str, Any] = {}
    if args_match:
        try:
            args = json.loads(args_match.group(1))
        except json.JSONDecodeError:
            args = {"raw": args_match.group(1)}
    return [{"tool": tool_match.group(1), "args": args}]


def _extract_plans(data: dict[str, Any]) -> list[str]:
    if "plan" in data:
        return [str(data["plan"])]
    return []
