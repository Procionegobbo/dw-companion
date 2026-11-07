"""Tests for `backend/domain/outcome.py`: resolving a roll into a move's band text."""

import pytest

from backend.domain.dice import Band, Roll
from backend.domain.outcome import Outcome, resolve_outcome
from backend.domain.rulebook import move_from_dict

from .domain_helpers import HACK_AND_SLASH, LAST_BREATH, MAKE_CAMP


@pytest.mark.parametrize(
    ("dice", "band", "text_key"),
    [
        ((5, 5), "strong_hit", "strong_hit"),
        ((3, 4), "weak_hit", "weak_hit"),
        ((1, 2), "miss", None),
    ],
)
def test_resolve_strong_weak_miss(
    dice: tuple[int, int], band: Band, text_key: str | None
) -> None:
    move = move_from_dict(HACK_AND_SLASH)
    outcome = resolve_outcome(move, Roll(dice=dice, modifier=0))
    assert outcome.band == band
    if text_key is None:
        assert outcome.text is None
    else:
        assert outcome.text == HACK_AND_SLASH["outcomes"][text_key]  # type: ignore[index]


def test_resolve_stated_miss() -> None:
    move = move_from_dict(LAST_BREATH)
    outcome = resolve_outcome(move, Roll(dice=(1, 1), modifier=0))
    assert outcome.band == "miss"
    assert outcome.text == LAST_BREATH["outcomes"]["miss"]  # type: ignore[index]


def test_resolve_requires_modifier() -> None:
    move = move_from_dict(HACK_AND_SLASH)
    with pytest.raises(ValueError, match="modifier is required"):
        resolve_outcome(move, Roll(dice=(3, 4), modifier=None))


def test_resolve_rejects_non_rolled_move() -> None:
    move = move_from_dict(MAKE_CAMP)
    with pytest.raises(ValueError, match="not rolled"):
        resolve_outcome(move, Roll(dice=(3, 4), modifier=0))


def test_outcome_text_is_verbatim() -> None:
    move = move_from_dict(HACK_AND_SLASH)
    outcome = resolve_outcome(move, Roll(dice=(5, 5), modifier=0))
    assert outcome.text is move.outcomes.strong_hit  # type: ignore[union-attr]


def test_outcome_invariants() -> None:
    mismatched_roll = Roll(dice=(5, 5), modifier=0)
    with pytest.raises(ValueError, match="band"):
        Outcome(move_id="hack-and-slash", roll=mismatched_roll, band="miss", text=None)

    rollless_roll = Roll(dice=(5, 5), modifier=None)
    with pytest.raises(ValueError, match="band"):
        Outcome(
            move_id="hack-and-slash", roll=rollless_roll, band="strong_hit", text=None
        )

    with pytest.raises(ValueError, match="text"):
        Outcome(
            move_id="hack-and-slash", roll=mismatched_roll, band="strong_hit", text=""
        )
