"""The `RulebookRepository` port: read-only access to parsed moves (D3).

Sync: the data is in-memory (spec 002's normalized JSON, loaded once).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.domain.rulebook import Move


class RulebookRepository(Protocol):
    def list_moves(self) -> Sequence[Move]: ...  # spec 002 document order
    def get_move(self, move_id: str) -> Move | None: ...
