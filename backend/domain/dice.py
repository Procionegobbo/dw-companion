"""Deterministic 2d6 + modifier dice resolution into Dungeon World bands.

Randomness is injected via `RandomSource` (D7): this module never imports `random` and
holds no global RNG. Callers (the graph's `roll` tool, spec 006) supply a
`random.Random` or a scripted fake; dice outcomes protect nothing, so the RNG need not
be cryptographic.
"""

from dataclasses import dataclass
from typing import Final, Literal, Protocol

Band = Literal["strong_hit", "weak_hit", "miss"]
BANDS: tuple[Band, ...] = ("strong_hit", "weak_hit", "miss")

MIN_MODIFIER: Final = -10
MAX_MODIFIER: Final = 10

_DIE_MIN: Final = 1
_DIE_MAX: Final = 6


class RandomSource(Protocol):
    def randint(self, a: int, b: int, /) -> int: ...


def band_for_total(total: int) -> Band:
    if total >= 10:
        return "strong_hit"
    if total >= 7:
        return "weak_hit"
    return "miss"


def band_label(band: Band) -> str:
    if band == "strong_hit":
        return "10+"
    if band == "weak_hit":
        return "7-9"
    return "6-"


def _validate_modifier(modifier: int, *, field: str) -> None:
    if isinstance(modifier, bool):
        raise ValueError(f"{field} must be an int, not bool")
    if modifier < MIN_MODIFIER or modifier > MAX_MODIFIER:
        raise ValueError(
            f"{field} must be between {MIN_MODIFIER} and {MAX_MODIFIER}, got {modifier}"
        )


@dataclass(frozen=True, slots=True)
class Roll:
    dice: tuple[int, int]
    modifier: int | None

    def __post_init__(self) -> None:
        if len(self.dice) != 2:
            raise ValueError(
                f"Roll.dice must have exactly two dice, got {len(self.dice)}"
            )
        for die in self.dice:
            if isinstance(die, bool):
                raise ValueError("Roll.dice values must be int, not bool")
            if die < _DIE_MIN or die > _DIE_MAX:
                raise ValueError(
                    f"Roll.dice values must be between {_DIE_MIN} and "
                    f"{_DIE_MAX}, got {die}"
                )
        if self.modifier is not None:
            _validate_modifier(self.modifier, field="Roll.modifier")

    @property
    def dice_total(self) -> int:
        return self.dice[0] + self.dice[1]

    @property
    def total(self) -> int | None:
        if self.modifier is None:
            return None
        return self.dice_total + self.modifier

    @property
    def band(self) -> Band | None:
        if self.total is None:
            return None
        return band_for_total(self.total)

    def band_with(self, modifier: int) -> Band:
        _validate_modifier(modifier, field="modifier")
        return band_for_total(self.dice_total + modifier)


def roll(rng: RandomSource, modifier: int | None = None) -> Roll:
    if modifier is not None:
        _validate_modifier(modifier, field="modifier")
    first = rng.randint(1, 6)
    second = rng.randint(1, 6)
    return Roll(dice=(first, second), modifier=modifier)
