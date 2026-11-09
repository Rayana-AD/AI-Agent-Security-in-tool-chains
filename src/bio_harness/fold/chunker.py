"""Semantic chunking for controlled shuffle folding."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ChunkType(str, Enum):
    FACT = "fact"
    PARAM = "param"
    ROUTE = "route"
    META = "meta"


TRANSIT_FIELD_PREFIXES = ("_", "signal_peptide", "gate_token", "routing_hint", "validation_")


@dataclass
class SemanticChunk:
    chunk_type: ChunkType
    text: str
    source_key: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()[:16]


class SemanticChunker:
    ROUTE_PATTERN = re.compile(
        r"(?i)(signal_peptide|_gate_token|_routing_hint|_validation_passed|routing_hint|gate_token)\s*[:=]\s*\S+"
    )
    META_PATTERN = re.compile(
        r"(?i)^(disclaimer|note|meta|i cannot|as an ai|however,)\b"
    )

    def split(self, output: str | dict[str, Any]) -> list[SemanticChunk]:
        if isinstance(output, dict):
            return self._split_dict(output)
        return self._split_text(str(output))

    def _split_dict(self, data: dict[str, Any]) -> list[SemanticChunk]:
        chunks: list[SemanticChunk] = []
        for key, value in data.items():
            text = f"{key}: {json.dumps(value, ensure_ascii=False)}"
            ctype = self._classify_key_value(key, str(value))
            chunks.append(SemanticChunk(chunk_type=ctype, text=text, source_key=key))
        return chunks

    def _split_text(self, text: str) -> list[SemanticChunk]:
        chunks: list[SemanticChunk] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            ctype = self._classify_line(line)
            chunks.append(SemanticChunk(chunk_type=ctype, text=line))
        if not chunks and text.strip():
            chunks.append(SemanticChunk(chunk_type=ChunkType.FACT, text=text.strip()))
        return chunks

    def _classify_key_value(self, key: str, value: str) -> ChunkType:
        kl = key.lower()
        if kl.startswith(TRANSIT_FIELD_PREFIXES) or "route" in kl or "gate" in kl:
            return ChunkType.ROUTE
        if kl in ("tool", "tool_name", "parameters", "args", "action"):
            return ChunkType.PARAM
        if kl in ("meta", "disclaimer", "note"):
            return ChunkType.META
        return ChunkType.FACT

    def _classify_line(self, line: str) -> ChunkType:
        if self.ROUTE_PATTERN.search(line):
            return ChunkType.ROUTE
        if self.META_PATTERN.match(line):
            return ChunkType.META
        if re.match(r"(?i)(tool|action|parameters?|args)\s*[:=]", line):
            return ChunkType.PARAM
        return ChunkType.FACT

    def reconstruct(self, chunks: list[SemanticChunk]) -> str:
        return "\n".join(c.text for c in chunks)

    def reconstruct_dict(self, chunks: list[SemanticChunk]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for c in chunks:
            if c.source_key:
                key = c.source_key
                _, _, rest = c.text.partition(": ")
                try:
                    result[key] = json.loads(rest)
                except json.JSONDecodeError:
                    result[key] = rest
            else:
                result[f"chunk_{c.content_hash}"] = c.text
        return result
