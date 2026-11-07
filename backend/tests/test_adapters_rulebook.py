"""Tests for the JSON rulebook repository (spec 007 Testing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.adapters.json_rulebook import JsonRulebookRepository
from backend.tests.domain_helpers import HACK_AND_SLASH, NAMED_MOVE_FIXTURES

_COMMITTED_MOVES = Path("data/normalized/moves.json")


def _write_moves(tmp_path: Path, data: object) -> Path:
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    (normalized_dir / "moves.json").write_text(json.dumps(data), encoding="utf-8")
    return normalized_dir


def test_loads_committed_moves() -> None:
    if not _COMMITTED_MOVES.exists():
        pytest.skip("data/normalized not built yet")

    repo = JsonRulebookRepository.from_dir(_COMMITTED_MOVES.parent)

    moves = repo.list_moves()
    assert len(moves) == 21
    expected_first_id = json.loads(_COMMITTED_MOVES.read_text(encoding="utf-8"))[0][
        "id"
    ]
    assert moves[0].id == expected_first_id
    move = repo.get_move("hack-and-slash")
    assert move is not None
    assert move.name == "Hack and Slash"


def test_get_unknown_move_returns_none(tmp_path: Path) -> None:
    normalized_dir = _write_moves(tmp_path, [HACK_AND_SLASH])
    repo = JsonRulebookRepository.from_dir(normalized_dir)

    assert repo.get_move("no-such-move") is None


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    normalized_dir = _write_moves(tmp_path, [HACK_AND_SLASH, HACK_AND_SLASH])

    with pytest.raises(ValueError, match="duplicate"):
        JsonRulebookRepository.from_dir(normalized_dir)


def test_invalid_file_names_path(tmp_path: Path) -> None:
    bad_move = {**HACK_AND_SLASH, "extra_key": "nope"}
    normalized_dir = _write_moves(tmp_path, [bad_move])

    with pytest.raises(ValueError, match="unexpected keys") as exc_info:
        JsonRulebookRepository.from_dir(normalized_dir)

    assert str(normalized_dir / "moves.json") in str(exc_info.value)


def test_top_level_must_be_array(tmp_path: Path) -> None:
    normalized_dir = _write_moves(tmp_path, {"not": "an array"})

    with pytest.raises(ValueError, match="array"):
        JsonRulebookRepository.from_dir(normalized_dir)


def test_list_moves_keeps_file_order(tmp_path: Path) -> None:
    normalized_dir = _write_moves(tmp_path, list(NAMED_MOVE_FIXTURES))
    repo = JsonRulebookRepository.from_dir(normalized_dir)

    assert [move.id for move in repo.list_moves()] == [
        fixture["id"] for fixture in NAMED_MOVE_FIXTURES
    ]
