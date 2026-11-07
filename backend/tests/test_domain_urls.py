"""Tests for `backend/domain/urls.py` (D21, spec 004 URL contract)."""

import pytest

from backend.domain.urls import move_url, section_url


def test_section_url() -> None:
    assert section_url("moves/hack-and-slash") == "/rules/moves/hack-and-slash/"
    assert section_url("moves") == "/rules/moves/"


def test_move_url() -> None:
    assert move_url("hack-and-slash") == "/moves/hack-and-slash/"


@pytest.mark.parametrize("bad_id", ["", "Moves", "moves/", "a b"])
def test_invalid_ids_rejected(bad_id: str) -> None:
    with pytest.raises(ValueError, match="invalid section_id"):
        section_url(bad_id)
    with pytest.raises(ValueError, match="invalid move_id"):
        move_url(bad_id)
