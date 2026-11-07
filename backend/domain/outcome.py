"""Pairs a resolved roll with a move's verbatim band text.

`resolve_outcome` never invents text: it only picks `move.outcomes.text_for(band)`
(D5, D11, D12). The LLM never produces dice values; only `backend.domain.dice.roll`
does, and this module only reads what that roll already decided.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.dice import Band, Roll
from backend.domain.rulebook import Move


@dataclass(frozen=True, slots=True)
class Outcome:
    move_id: str
    roll: Roll
    band: Band
    text: str | None

    def __post_init__(self) -> None:
        if self.roll.band is None:
            raise ValueError("invalid outcome: roll must have a band")
        if self.band != self.roll.band:
            raise ValueError("invalid outcome: band must equal roll.band")
        if self.text is not None and self.text == "":
            raise ValueError("invalid outcome: text must be null or non-empty")


def resolve_outcome(move: Move, roll: Roll) -> Outcome:
    if move.outcomes is None:
        raise ValueError(f"cannot resolve move {move.id!r}: it is not rolled")
    if roll.modifier is None:
        raise ValueError(f"cannot resolve move {move.id!r}: modifier is required")
    band = roll.band
    assert band is not None  # modifier is not None, so Roll.band is not None
    return Outcome(
        move_id=move.id,
        roll=roll,
        band=band,
        text=move.outcomes.text_for(band),
    )
