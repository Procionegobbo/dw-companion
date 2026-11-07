"""The hybrid (vector + BM25) retriever: `HybridRetriever` (D7).

Fuses the top `CANDIDATES` vector hits with the top `CANDIDATES` BM25 hits via
Reciprocal Rank Fusion, then deduplicates by `section_id` (first, i.e. best-ranked,
wins) and cuts to `k`, satisfying the `ports.retriever.Retriever` contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
from numpy.typing import NDArray

from backend.adapters.retrieval.bm25 import BM25Index
from backend.adapters.retrieval.embedder import Embedder
from backend.adapters.retrieval.index import LoadedIndex
from backend.ports.errors import PortError
from backend.ports.retriever import RetrievedChunk

CANDIDATES: Final = 30
RRF_K: Final = 60


def _top_ranks(candidates: Sequence[tuple[int, float]], limit: int) -> dict[int, int]:
    """Ranks (1-based) of the top `limit` candidates, highest score first, ties broken
    by the lower chunk index."""
    ordered = sorted(candidates, key=lambda item: (-item[1], item[0]))[:limit]
    return {chunk_index: rank for rank, (chunk_index, _score) in enumerate(ordered, 1)}


class HybridRetriever:
    """Satisfies `ports.retriever.Retriever` (D7)."""

    def __init__(self, index: LoadedIndex, embedder: Embedder) -> None:
        self._index = index
        self._embedder = embedder
        self._bm25 = BM25Index([chunk.index_text for chunk in index.chunks])

    async def retrieve(self, query: str, k: int) -> Sequence[RetrievedChunk]:
        if k < 1:
            raise ValueError("invalid HybridRetriever.retrieve: k must be >= 1")
        if not query.strip():
            return []

        vectors = await self._embedder.embed([query])
        query_vector = np.asarray(vectors[0], dtype=np.float64)
        norm = float(np.linalg.norm(query_vector))
        if norm == 0.0:
            raise PortError("query embedding is a zero vector")
        unit_query = (query_vector / norm).astype(np.float32)

        cosine_scores: NDArray[np.float32] = self._index.embeddings @ unit_query
        vector_candidates = [(i, float(score)) for i, score in enumerate(cosine_scores)]
        vector_ranks = _top_ranks(vector_candidates, CANDIDATES)

        bm25_scores = self._bm25.scores(query)
        bm25_hits = [(i, score) for i, score in enumerate(bm25_scores) if score > 0.0]
        bm25_ranks = _top_ranks(bm25_hits, CANDIDATES)

        fused: dict[int, float] = {}
        for chunk_index, rank in vector_ranks.items():
            fused[chunk_index] = fused.get(chunk_index, 0.0) + 1.0 / (RRF_K + rank)
        for chunk_index, rank in bm25_ranks.items():
            fused[chunk_index] = fused.get(chunk_index, 0.0) + 1.0 / (RRF_K + rank)

        ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))

        results: list[RetrievedChunk] = []
        seen_section_ids: set[str] = set()
        for chunk_index, score in ordered:
            chunk = self._index.chunks[chunk_index]
            if chunk.section_id in seen_section_ids:
                continue
            seen_section_ids.add(chunk.section_id)
            results.append(
                RetrievedChunk(
                    section_id=chunk.section_id,
                    title=chunk.title,
                    chapter=chunk.chapter,
                    anchor_url=chunk.anchor_url,
                    type=chunk.type,
                    text=chunk.text,
                    score=score,
                )
            )
            if len(results) == k:
                break
        return results
