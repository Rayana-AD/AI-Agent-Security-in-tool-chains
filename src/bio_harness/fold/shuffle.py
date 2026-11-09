"""Seeded controlled shuffle for semantic chunks."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from bio_harness.fold.chunker import ChunkType, SemanticChunk


@dataclass
class ShuffleResult:
    chunks: list[SemanticChunk]
    rounds: int
    permutations: list[list[int]]


def _seed_from(session_id: str, round_i: int, salt: str = "") -> int:
    h = hashlib.sha256(f"{session_id}:{round_i}:{salt}".encode()).hexdigest()
    return int(h[:16], 16)


def seeded_permutation(seed: int, n: int) -> list[int]:
    rng = random.Random(seed)
    perm = list(range(n))
    rng.shuffle(perm)
    return perm


def intra_type_shuffle(chunks: list[SemanticChunk], seed: int) -> list[SemanticChunk]:
    """Shuffle within each chunk type, preserving type block order."""
    by_type: dict[ChunkType, list[SemanticChunk]] = {}
    type_order: list[ChunkType] = []
    for c in chunks:
        if c.chunk_type not in by_type:
            by_type[c.chunk_type] = []
            type_order.append(c.chunk_type)
        by_type[c.chunk_type].append(c)

    rng = random.Random(seed)
    result: list[SemanticChunk] = []
    for t in type_order:
        group = by_type[t][:]
        rng.shuffle(group)
        result.extend(group)
    return result


def controlled_shuffle(
    chunks: list[SemanticChunk],
    *,
    session_id: str,
    rounds: int = 2,
) -> ShuffleResult:
    current = list(chunks)
    perms: list[list[int]] = []
    for round_i in range(rounds):
        seed = _seed_from(session_id, round_i)
        perm = seeded_permutation(seed, len(current))
        perms.append(perm)
        current = [current[i] for i in perm]
        current = intra_type_shuffle(current, seed + 1)
    return ShuffleResult(chunks=current, rounds=rounds, permutations=perms)
