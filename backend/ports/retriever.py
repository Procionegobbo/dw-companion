"""The `Retriever` port: ranked chunks for the rules branch (D3).

Async because it does I/O against the vector store (spec 007).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

ChunkType = Literal["section", "move"]


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    section_id: str
    title: str
    chapter: str
    anchor_url: str
    type: ChunkType
    text: str
    score: float

    def __post_init__(self) -> None:
        if not self.section_id.strip():
            raise ValueError("invalid RetrievedChunk: section_id must be non-empty")
        if not self.title.strip():
            raise ValueError("invalid RetrievedChunk: title must be non-empty")
        if not self.chapter.strip():
            raise ValueError("invalid RetrievedChunk: chapter must be non-empty")
        if not (self.anchor_url.startswith("/") and self.anchor_url.endswith("/")):
            raise ValueError(
                "invalid RetrievedChunk: anchor_url must start and end with '/'"
            )
        if self.type not in ("section", "move"):
            raise ValueError("invalid RetrievedChunk: type must be 'section' or 'move'")
        if not math.isfinite(self.score):
            raise ValueError("invalid RetrievedChunk: score must be a finite float")


class Retriever(Protocol):
    async def retrieve(self, query: str, k: int) -> Sequence[RetrievedChunk]: ...

    # contract: len <= k, distinct section_id, most relevant first, may be empty;
    # raises PortError
