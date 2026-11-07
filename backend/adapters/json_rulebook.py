"""JSON-backed `RulebookRepository` over the spec 002 normalized `moves.json` (D24).

Loads only `moves.json`: sections are read by the retriever's own index (spec 007
`retrieval/`), not by this repository.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from backend.domain.rulebook import Move, move_from_dict


class JsonRulebookRepository:
    """Satisfies `ports.rulebook.RulebookRepository` over a list of parsed moves."""

    def __init__(self, moves: Sequence[Move]) -> None:
        self._moves = tuple(moves)
        self._by_id: dict[str, Move] = {}
        for move in self._moves:
            if move.id in self._by_id:
                raise ValueError(f"invalid rulebook: duplicate move id {move.id!r}")
            self._by_id[move.id] = move

    @classmethod
    def from_dir(cls, normalized_dir: Path) -> JsonRulebookRepository:
        path = normalized_dir / "moves.json"
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid rulebook {path}: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"invalid rulebook {path}: top level must be a JSON array")
        items = cast("list[object]", data)
        moves: list[Move] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError(
                    f"invalid rulebook {path}: array elements must be objects"
                )
            try:
                moves.append(move_from_dict(cast("Mapping[str, object]", item)))
            except ValueError as exc:
                raise ValueError(f"invalid rulebook {path}: {exc}") from exc
        return cls(moves)

    def list_moves(self) -> Sequence[Move]:
        return self._moves

    def get_move(self, move_id: str) -> Move | None:
        return self._by_id.get(move_id)
