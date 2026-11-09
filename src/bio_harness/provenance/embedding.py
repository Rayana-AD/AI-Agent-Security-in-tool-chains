"""Frozen text embedders for provenance feature extraction (no fine-tuning)."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, runtime_checkable

import numpy as np

TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")
DEFAULT_EMBED_DIM = 384
DEFAULT_PROJ_DIM = 32


@runtime_checkable
class EmbeddingBackend(Protocol):
    name: str
    embed_dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return (n, embed_dim) L2-normalized rows."""


def _l2_normalize(rows: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-9)
    return rows / norms


class HashEmbeddingBackend:
    """Deterministic char-trigram hashing — fast, no downloads (tests / CI)."""

    name = "hash"
    embed_dim = DEFAULT_EMBED_DIM

    def encode(self, texts: list[str]) -> np.ndarray:
        rows = np.zeros((len(texts), self.embed_dim), dtype=np.float64)
        for i, text in enumerate(texts):
            tl = text.lower()
            tokens = TOKEN_RE.findall(tl)
            grams: list[str] = tokens[:]
            for tok in tokens:
                if len(tok) >= 3:
                    for j in range(len(tok) - 2):
                        grams.append(tok[j : j + 3])
            for g in grams:
                h = int(hashlib.sha256(g.encode()).hexdigest(), 16)
                idx = h % self.embed_dim
                sign = 1.0 if (h >> 8) & 1 else -1.0
                rows[i, idx] += sign
        return _l2_normalize(rows)


class SentenceTransformerBackend:
    """Frozen MiniLM encoder (lazy-loaded)."""

    name = "minilm"
    embed_dim = DEFAULT_EMBED_DIM

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        vecs = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float64)


def get_embedding_backend(name: str = "hash") -> EmbeddingBackend:
    if name in ("hash", "hash384"):
        return HashEmbeddingBackend()
    if name in ("minilm", "sentence-transformers/all-MiniLM-L6-v2"):
        return SentenceTransformerBackend()
    raise ValueError(f"Unknown embedding backend: {name}")


def make_projection_matrix(
    embed_dim: int = DEFAULT_EMBED_DIM,
    proj_dim: int = DEFAULT_PROJ_DIM,
    *,
    seed: int = 42,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mat = rng.standard_normal((proj_dim, embed_dim), dtype=np.float64)
    mat /= np.sqrt(embed_dim)
    return mat


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def embedding_pair_features(
    goal: str,
    untrusted: str,
    proposed: str,
    backend: EmbeddingBackend,
    projector: np.ndarray,
) -> list[float]:
    """Projected triple embeddings + pairwise cosines."""
    embs = backend.encode([goal, untrusted, proposed])
    projected = projector @ embs.T  # (proj_dim, 3)
    feats: list[float] = []
    feats.extend(projected[:, 0].tolist())
    feats.extend(projected[:, 1].tolist())
    feats.extend(projected[:, 2].tolist())
    feats.append(cosine(embs[0], embs[1]))
    feats.append(cosine(embs[0], embs[2]))
    feats.append(cosine(embs[1], embs[2]))
    return feats


def embedding_feature_dim(proj_dim: int = DEFAULT_PROJ_DIM) -> int:
    return 3 * proj_dim + 3
