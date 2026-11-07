"""Hand-written fake for the `RulebookRepository` port (spec 006 Testing)."""

from __future__ import annotations

from collections.abc import Sequence

from backend.domain.rulebook import Move


class FakeRulebookRepository:
    def __init__(self, moves: Sequence[Move]) -> None:
        self._moves = list(moves)
        self._by_id = {move.id: move for move in self._moves}

    def list_moves(self) -> Sequence[Move]:
        return list(self._moves)

    def get_move(self, move_id: str) -> Move | None:
        return self._by_id.get(move_id)
