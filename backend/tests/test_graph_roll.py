"""Tests for the `roll` and `outcome` nodes (spec 006 Testing).

Rolling is opt-in per turn and only happens for a matched, rolled move (D6, D7):
the dice always come from `backend.domain.dice.roll`, never from the LLM, and the
outcome text is quoted verbatim from the move's own `Outcomes` by
`backend.domain.outcome.resolve_outcome`.
"""

from __future__ import annotations

import asyncio
import random

from backend.ports.errors import PortError
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.graph_helpers import (
    MOVES,
    classifier_json,
    make_assistant,
    router_json,
    turn,
)

_HACK_AND_SLASH = next(move for move in MOVES if move.id == "hack-and-slash")
_LAST_BREATH = next(move for move in MOVES if move.id == "last-breath")
assert _HACK_AND_SLASH.outcomes is not None
assert _LAST_BREATH.outcomes is not None
_HACK_AND_SLASH_STRONG_HIT = _HACK_AND_SLASH.outcomes.strong_hit
_LAST_BREATH_MISS = _LAST_BREATH.outcomes.miss


def _action_llm(
    classifier_text: str | PortError, *, answer: str | PortError = "Explanation."
) -> FakeLLMClient:
    return FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_text],
            "answer": [answer],
        }
    )


def test_roll_with_modifier_resolves_outcome() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    rng = ScriptedRandom([4, 5])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(
        assistant.run(turn("I attack the orc", roll_requested=True, modifier=1))
    )

    assert result.reply.move is not None
    assert result.reply.move.roll is not None
    assert result.reply.move.roll.dice == (4, 5)
    assert result.reply.move.outcome is not None
    assert result.reply.move.outcome.band == "strong_hit"
    assert result.reply.move.outcome.text is _HACK_AND_SLASH_STRONG_HIT
    assert result.reply.text.endswith("Rolled 4 + 5 + 1 = 10: 10+.")


def test_roll_negative_modifier_text() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    rng = ScriptedRandom([3, 3])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(
        assistant.run(turn("I attack the orc", roll_requested=True, modifier=-1))
    )

    assert result.reply.text.endswith("Rolled 3 + 3 - 1 = 5: 6-.")
    assert result.reply.move is not None
    assert result.reply.move.outcome is not None
    assert result.reply.move.outcome.text is None


def test_roll_stated_miss() -> None:
    llm = _action_llm(classifier_json("last-breath", confidence=0.9))
    rng = ScriptedRandom([1, 1])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(
        assistant.run(turn("I'm dying", roll_requested=True, modifier=0))
    )

    assert result.reply.move is not None
    assert result.reply.move.outcome is not None
    assert result.reply.move.outcome.text == _LAST_BREATH_MISS


def test_roll_without_modifier_reports_bands() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    rng = ScriptedRandom([3, 5])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(
        assistant.run(turn("I attack the orc", roll_requested=True, modifier=None))
    )

    assert result.reply.move is not None
    assert result.reply.move.outcome is None
    assert result.reply.move.bands_by_modifier == (
        (-3, "miss"),
        (-2, "miss"),
        (-1, "weak_hit"),
        (0, "weak_hit"),
        (1, "weak_hit"),
        (2, "strong_hit"),
        (3, "strong_hit"),
    )
    assert result.reply.text.endswith(
        "Rolled 3 + 5 = 8. Add your modifier: -3 to -2: 6-; -1 to +1: 7-9; "
        "+2 to +3: 10+."
    )


def test_no_roll_unless_requested() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    rng = ScriptedRandom([])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(assistant.run(turn("I attack the orc", roll_requested=False)))

    assert rng.calls == []
    assert result.reply.move is not None
    assert result.reply.move.roll is None


def test_non_rolled_move_is_not_rolled() -> None:
    llm = _action_llm(classifier_json("make-camp", confidence=0.9))
    rng = ScriptedRandom([])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(assistant.run(turn("I make camp", roll_requested=True)))

    assert rng.calls == []
    assert result.reply.text.endswith(
        "Make Camp isn't rolled, so there is nothing to roll."
    )


def test_no_move_with_roll_requested() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("no_move", confidence=0.9)],
        }
    )
    rng = ScriptedRandom([])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(assistant.run(turn("I walk into town", roll_requested=True)))

    assert rng.calls == []
    assert result.reply.text.endswith(" There is nothing to roll.")


def test_clarification_never_rolls() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash", confidence=0.4)],
        }
    )
    rng = ScriptedRandom([])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(assistant.run(turn("I attack the orc", roll_requested=True)))

    assert rng.calls == []
    assert result.reply.kind == "clarification"


def test_seeded_rng_reproducible() -> None:
    def _run() -> tuple[int, int]:
        llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
        assistant, _ = make_assistant(llm, rng=random.Random(42))
        result = asyncio.run(
            assistant.run(turn("I attack the orc", roll_requested=True, modifier=1))
        )
        assert result.reply.move is not None
        assert result.reply.move.roll is not None
        return result.reply.move.roll.dice

    assert _run() == _run()
