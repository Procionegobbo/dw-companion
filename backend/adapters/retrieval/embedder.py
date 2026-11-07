"""The `Embedder` protocol (spec 007 D1): texts in, unit vectors out.

Used by `OpenRouterEmbedder` (`backend/adapters/openrouter.py`), the index build CLI
and the hybrid retriever (story 3). Kept separate from `openrouter.py` so the build CLI
and `HybridRetriever` depend on the protocol, not the concrete adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    # contract: same order and length as `texts`; `texts == []` returns `[]` with no
    # request; raises PortError
