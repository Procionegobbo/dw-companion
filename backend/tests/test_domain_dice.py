"""Tests for `backend/domain/dice.py`: bands, modifiers and injected randomness."""

import dataclasses
import random
from typing import cast

import pytest

from backend.domain.dice import (
    MAX_MODIFIER,
    MIN_MODIFIER,
    Band,
    Roll,
    band_for_total,
    band_label,
    roll,
)

from .domain_helpers import ScriptedRandom


@pytest.mark.parametrize(
    ("total", "expected"),
    [(6, "miss"), (7, "weak_hit"), (9, "weak_hit"), (10, "strong_hit")],
)
def test_band_boundaries(total: int, expected: Band) -> None:
    assert band_for_total(total) == expected


@pytest.mark.parametrize("total", range(-8, 23))
def test_band_for_every_reachable_total(total: int) -> None:
    band = band_for_total(total)
    if total >= 10:
        assert band == "strong_hit"
    elif total >= 7:
        assert band == "weak_hit"
    else:
        assert band == "miss"


def test_band_for_extreme_totals() -> None:
    assert band_for_total(-100) == "miss"
    assert band_for_total(100) == "strong_hit"


@pytest.mark.parametrize(
    ("band", "label"),
    [("strong_hit", "10+"), ("weak_hit", "7-9"), ("miss", "6-")],
)
def test_band_label(band: Band, label: str) -> None:
    assert band_label(band) == label


def test_roll_uses_two_d6_draws_in_order() -> None:
    rng = ScriptedRandom([3, 5])
    result = roll(rng)
    assert result.dice == (3, 5)
    assert rng.calls == [(1, 6), (1, 6)]


@pytest.mark.parametrize(
    ("dice", "modifier", "total", "band"),
    [
        ((3, 3), 0, 6, "miss"),
        ((3, 3), 1, 7, "weak_hit"),
        ((4, 5), 0, 9, "weak_hit"),
        ((4, 5), 1, 10, "strong_hit"),
        ((1, 1), -3, -1, "miss"),
        ((6, 6), 3, 15, "strong_hit"),
    ],
)
def test_roll_with_modifier_totals_and_bands(
    dice: tuple[int, int], modifier: int, total: int, band: Band
) -> None:
    result = Roll(dice=dice, modifier=modifier)
    assert result.total == total
    assert result.band == band


def test_roll_without_modifier_has_no_total_or_band() -> None:
    result = Roll(dice=(3, 5), modifier=None)
    assert result.modifier is None
    assert result.total is None
    assert result.band is None
    assert result.dice_total == 8


@pytest.mark.parametrize(
    ("modifier", "expected"),
    [(-2, "miss"), (-1, "weak_hit"), (1, "weak_hit"), (2, "strong_hit")],
)
def test_band_with_reports_band_per_modifier(modifier: int, expected: Band) -> None:
    result = Roll(dice=(3, 5), modifier=None)
    assert result.band_with(modifier) == expected


def test_roll_band_matches_band_for_total_exhaustively() -> None:
    for d1 in range(1, 7):
        for d2 in range(1, 7):
            for modifier in range(MIN_MODIFIER, MAX_MODIFIER + 1):
                result = Roll(dice=(d1, d2), modifier=modifier)
                assert result.band == band_for_total(d1 + d2 + modifier)


@pytest.mark.parametrize("modifier", [-11, 11])
def test_modifier_out_of_range_rejected(modifier: int) -> None:
    rng = ScriptedRandom([3, 3])
    with pytest.raises(ValueError, match="modifier"):
        roll(rng, modifier)
    assert rng.calls == [], "roll must validate the modifier before drawing"
    with pytest.raises(ValueError, match="modifier"):
        Roll(dice=(3, 3), modifier=modifier)
    with pytest.raises(ValueError, match="modifier"):
        Roll(dice=(3, 3), modifier=None).band_with(modifier)


def test_modifier_bounds_accepted() -> None:
    assert roll(ScriptedRandom([3, 3]), MIN_MODIFIER).modifier == MIN_MODIFIER
    assert roll(ScriptedRandom([3, 3]), MAX_MODIFIER).modifier == MAX_MODIFIER
    assert Roll(dice=(3, 3), modifier=MIN_MODIFIER).modifier == MIN_MODIFIER
    assert Roll(dice=(3, 3), modifier=MAX_MODIFIER).modifier == MAX_MODIFIER
    assert Roll(dice=(3, 3), modifier=None).band_with(MIN_MODIFIER) == "miss"
    assert Roll(dice=(3, 3), modifier=None).band_with(MAX_MODIFIER) == "strong_hit"


def test_bool_modifier_rejected() -> None:
    with pytest.raises(ValueError, match="bool"):
        roll(ScriptedRandom([3, 3]), True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bool"):
        Roll(dice=(3, 3), modifier=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bool"):
        Roll(dice=(3, 3), modifier=None).band_with(True)  # type: ignore[arg-type]


def test_die_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match="dice"):
        roll(ScriptedRandom([0, 3]))
    with pytest.raises(ValueError, match="dice"):
        roll(ScriptedRandom([3, 7]))
    with pytest.raises(ValueError, match="dice"):
        Roll(dice=cast(tuple[int, int], (1, 2, 3)), modifier=None)


def test_seeded_rolls_are_reproducible() -> None:
    rng_a = random.Random(1234)
    rng_b = random.Random(1234)
    results_a = [roll(rng_a, 1) for _ in range(50)]
    results_b = [roll(rng_b, 1) for _ in range(50)]
    assert results_a == results_b


def test_seeded_rolls_cover_all_faces() -> None:
    rng = random.Random(7)
    seen: set[int] = set()
    for _ in range(1000):
        result = roll(rng)
        for die in result.dice:
            assert 1 <= die <= 6
            seen.add(die)
    assert seen == {1, 2, 3, 4, 5, 6}


def test_random_random_works_as_random_source() -> None:
    result = roll(random.Random(0), 1)
    assert result.dice[0] in range(1, 7)
    assert result.dice[1] in range(1, 7)
    assert result.total == result.dice_total + 1


def test_roll_is_immutable() -> None:
    result = Roll(dice=(3, 5), modifier=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.modifier = 1  # type: ignore[misc]
