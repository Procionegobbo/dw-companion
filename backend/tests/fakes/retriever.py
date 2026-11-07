"""Hand-written fake for the `Retriever` port (spec 006 Testing)."""

from __future__ import annotations

from collections.abc import Sequence

from backend.ports.errors import PortError
from backend.ports.retriever import RetrievedChunk


class FakeRetriever:
    def __init__(
        self,
        chunks: Sequence[RetrievedChunk] = (),
        error: PortError | None = None,
    ) -> None:
        ids = [chunk.section_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise AssertionError("FakeRetriever: chunks must have distinct section_id")
        self._chunks = list(chunks)
        self._error = error
        self.calls: list[tuple[str, int]] = []

    async def retrieve(self, query: str, k: int) -> Sequence[RetrievedChunk]:
        self.calls.append((query, k))
        if self._error is not None:
            raise self._error
        return self._chunks[:k]
