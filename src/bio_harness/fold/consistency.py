"""Semantic consistency check after shuffle reconstruction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bio_harness.fold.chunker import SemanticChunk, SemanticChunker


@dataclass
class ConsistencyResult:
    passed: bool
    score: float
    reason: str = ""


class ConsistencyChecker:
    def __init__(
        self,
        embedding_threshold: float = 0.75,
        use_embeddings: bool = True,
    ) -> None:
        self.embedding_threshold = embedding_threshold
        self.use_embeddings = use_embeddings
        self._model = None

    def _load_embeddings(self):
        if self._model is None and self.use_embeddings:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self._model = False
        return self._model

    def check(self, original: str, reconstructed: str) -> ConsistencyResult:
        orig_norm = _normalize(original)
        recon_norm = _normalize(reconstructed)
        if orig_norm == recon_norm:
            return ConsistencyResult(passed=True, score=1.0)

        orig_facts = _extract_fact_set(original)
        recon_facts = _extract_fact_set(reconstructed)
        if orig_facts and not orig_facts.issubset(recon_facts):
            missing = orig_facts - recon_facts
            return ConsistencyResult(
                passed=False,
                score=len(orig_facts & recon_facts) / max(len(orig_facts), 1),
                reason=f"missing_facts_after_shuffle:{missing}",
            )

        if _detect_contradiction(original, reconstructed):
            return ConsistencyResult(
                passed=False,
                score=0.0,
                reason="contradiction_detected",
            )

        emb = self._load_embeddings()
        if emb and emb is not False:
            import numpy as np

            vecs = emb.encode([original, reconstructed])
            sim = float(np.dot(vecs[0], vecs[1]) / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1]) + 1e-9))
            passed = sim >= self.embedding_threshold
            return ConsistencyResult(
                passed=passed,
                score=sim,
                reason="" if passed else f"embedding_sim_below_threshold:{sim:.3f}",
            )

        overlap = _token_overlap(orig_norm, recon_norm)
        passed = overlap >= 0.6
        return ConsistencyResult(
            passed=passed,
            score=overlap,
            reason="" if passed else f"token_overlap_low:{overlap:.3f}",
        )

    def check_chunks(
        self,
        original_chunks: list[SemanticChunk],
        shuffled_chunks: list[SemanticChunk],
    ) -> ConsistencyResult:
        chunker = SemanticChunker()
        return self.check(
            chunker.reconstruct(original_chunks),
            chunker.reconstruct(shuffled_chunks),
        )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_fact_set(text: str) -> set[str]:
    facts = set()
    for line in text.splitlines():
        line = line.strip()
        if line and not re.match(r"(?i)(signal_peptide|_gate|_routing|meta|disclaimer)", line):
            facts.add(_normalize(line))
    return facts


def _token_overlap(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_CONTRADICTION_PAIRS = [
    ("approve", "deny"),
    ("allow", "block"),
    ("safe", "harmful"),
    ("send email", "do not send"),
    ("execute", "refuse"),
]


def _detect_contradiction(a: str, b: str) -> bool:
    al, bl = a.lower(), b.lower()
    for p, n in _CONTRADICTION_PAIRS:
        if (p in al and n in bl) or (n in al and p in bl):
            if al != bl:
                return True
    return False
