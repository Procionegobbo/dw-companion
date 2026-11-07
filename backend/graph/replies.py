"""Fixed user-facing copy (spec 006 User-Facing Copy).

Out-of-scope, error, not-found, clarification, roll-phrase and roll-result copy.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from backend.domain.dice import Band, Roll, band_label
from backend.domain.rulebook import AbilityStat, Move
from backend.graph.llm_outputs import NO_MOVE
from backend.graph.state import Reply

OUT_OF_SCOPE_TEXT: Final = (
    "I can help with Dungeon World: ask me a rules question (for example, "
    '"How does Hold work?") or describe what your character does, and '
    "I'll tell you which move it triggers and how to roll it."
)

ERROR_TEXT: Final = (
    "Sorry, something went wrong while answering. Please try again or "
    "rephrase your message."
)

NOT_FOUND_TEXT: Final = "I couldn't find this in the rules."

NOT_ROLLED_TEXT: Final = "{name} isn't rolled, so there is nothing to roll."

_CLARIFY_SUFFIX: Final = "Tell me a bit more about what your character is trying to do."


def error_reply() -> Reply:
    return Reply(kind="error", text=ERROR_TEXT)


def no_move_text(rationale: str, roll_requested: bool) -> str:
    text = "No move is triggered."
    stripped_rationale = rationale.strip()
    if stripped_rationale:
        text += f" {stripped_rationale}"
    if roll_requested:
        text += " There is nothing to roll."
    return text


def _lower_first(text: str) -> str:
    if not text:
        return text
    return text[0].lower() + text[1:]


def _render_option(option: Move | str) -> str:
    if option == NO_MOVE:
        return "no move at all"
    assert isinstance(option, Move)
    return f"{option.name} ({_lower_first(option.trigger)})"


def clarification_text(options: Sequence[Move | str]) -> str:
    rendered = [_render_option(option) for option in options]
    if not rendered:
        return f"I'm not sure which move this is. {_CLARIFY_SUFFIX}"
    if len(rendered) == 1:
        return f"I'm not sure this is {rendered[0]}. {_CLARIFY_SUFFIX}"
    joined = f"{', '.join(rendered[:-1])} or {rendered[-1]}"
    return f"I'm not sure which move this is. Do you mean {joined}? {_CLARIFY_SUFFIX}"


def roll_phrase(move: Move, roll_stat: AbilityStat | None) -> str:
    if roll_stat is not None:
        return f"roll+{roll_stat}"
    if move.stat == "VARIES":
        return "roll+the stat that matches how you act (DEX, CON, INT, WIS, STR or CHA)"
    if move.stat == "BOND":
        return "roll+Bond"
    if move.stat == "NONE":
        return "roll 2d6 with no stat added"
    return "not rolled"


def _format_modifier(modifier: int) -> str:
    if modifier > 0:
        return f"+{modifier}"
    return str(modifier)


def roll_text_with_modifier(roll: Roll) -> str:
    modifier = roll.modifier
    total = roll.total
    band = roll.band
    if modifier is None or total is None or band is None:
        raise ValueError("roll_text_with_modifier requires a roll with a modifier")
    sign = "+" if modifier >= 0 else "-"
    return (
        f"Rolled {roll.dice[0]} + {roll.dice[1]} {sign} {abs(modifier)} = "
        f"{total}: {band_label(band)}."
    )


def roll_text_without_modifier(roll: Roll) -> str:
    bands: list[tuple[int, Band]] = [(m, roll.band_with(m)) for m in range(-3, 4)]
    groups: list[tuple[int, int, Band]] = []
    start, current_band = bands[0]
    end = start
    for modifier, band in bands[1:]:
        if band == current_band:
            end = modifier
            continue
        groups.append((start, end, current_band))
        start = end = modifier
        current_band = band
    groups.append((start, end, current_band))

    rendered_groups = [
        f"{_format_modifier(lo)}: {band_label(band)}"
        if lo == hi
        else f"{_format_modifier(lo)} to {_format_modifier(hi)}: {band_label(band)}"
        for lo, hi, band in groups
    ]
    joined = "; ".join(rendered_groups)
    return (
        f"Rolled {roll.dice[0]} + {roll.dice[1]} = {roll.dice_total}. "
        f"Add your modifier: {joined}."
    )
