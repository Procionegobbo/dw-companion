"""A deterministic `Embedder` fake (spec 007 D21): no network, no real model.

Each text becomes a hashed bag-of-words vector over spec 007's BM25 tokenizer, so the
same text always embeds to the same vector and different texts tend to differ.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from backend.adapters.retrieval.bm25 import tokenize
from backend.ports.errors import PortError


class FakeEmbedder:
    """Satisfies `retrieval.embedder.Embedder`. Records every `embed` call's texts."""

    def __init__(self, dim: int = 64, error: PortError | None = None) -> None:
        self.dim = dim
        self.error = error
        self.calls: list[Sequence[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.error is not None:
            raise self.error
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in tokenize(text):
            index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            vector[index % self.dim] += 1.0
        if all(value == 0.0 for value in vector):
            vector[0] = 1.0
        return vector
