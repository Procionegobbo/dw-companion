"""Tests for the move branch: `classify_move`, `clarify`, `no_move` and `explain`
(spec 006 Testing).
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from backend.domain.rulebook import AbilityStat, Move, move_from_dict
from backend.graph.replies import clarification_text, roll_phrase
from backend.ports.errors import PortError
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.rulebook import FakeRulebookRepository
from backend.tests.graph_helpers import (
    MOVES,
    classifier_json,
    make_assistant,
    router_json,
    turn,
)

_BOND_MOVE_FIXTURE: dict[str, object] = {
    "id": "aid-another",
    "name": "Aid Another",
    "category": "basic",
    "class": None,
    "stat": "BOND",
    "trigger": "When you help or hinder another character's roll with a bond",
    "outcomes": {
        "strong_hit": "On a 10+ you grant them +1 or impose -1.",
        "weak_hit": "On a 7-9 you still help but expose yourself to danger.",
        "miss": None,
    },
    "body_markdown": "(body)",
    "section_id": "moves/aid-another",
}
BOND_MOVE = move_from_dict(_BOND_MOVE_FIXTURE)


def _move(move_id: str) -> Move:
    return next(move for move in MOVES if move.id == move_id)


HACK_AND_SLASH_MOVE = _move("hack-and-slash")
DEFY_DANGER_MOVE = _move("defy-danger")
LAST_BREATH_MOVE = _move("last-breath")
MAKE_CAMP_MOVE = _move("make-camp")


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


def test_classifier_receives_all_candidate_moves() -> None:
    llm = _action_llm(classifier_json("hack-and-slash"))
    retriever = FakeRetriever()
    assistant, _ = make_assistant(llm, retriever=retriever)

    asyncio.run(assistant.run(turn("I attack the orc")))

    request = next(r for r in llm.requests if r.role == "classifier")
    assert request.role == "classifier"
    assert request.temperature == 0.0
    assert request.max_tokens == 400
    for move in MOVES:
        assert move.id in request.user
        assert move.trigger in request.user

    assert request.response_schema is not None
    properties = cast(dict[str, object], request.response_schema["properties"])
    move_id_schema = cast(dict[str, object], properties["move_id"])
    expected_enum = [move.id for move in MOVES] + ["no_move"]
    assert move_id_schema["enum"] == expected_enum
    assert retriever.calls == []


def test_class_moves_excluded_from_candidates() -> None:
    class_move_fixture: dict[str, object] = {
        "id": "a-class-move",
        "name": "A Class Move",
        "category": "class",
        "class": "fighter",
        "stat": None,
        "trigger": "When you do a class thing",
        "outcomes": None,
        "body_markdown": "(body)",
        "section_id": "moves/a-class-move",
    }
    class_move = move_from_dict(class_move_fixture)

    llm = _action_llm(classifier_json("hack-and-slash"))
    assistant, _ = make_assistant(
        llm, rulebook=FakeRulebookRepository([*MOVES, class_move])
    )

    asyncio.run(assistant.run(turn("I attack the orc")))

    request = next(r for r in llm.requests if r.role == "classifier")
    assert class_move.id not in request.user
    assert class_move.trigger not in request.user
    assert request.response_schema is not None
    properties = cast(dict[str, object], request.response_schema["properties"])
    move_id_schema = cast(dict[str, object], properties["move_id"])
    assert class_move.id not in cast(list[str], move_id_schema["enum"])


def test_confident_move_explained_with_verbatim_outcomes() -> None:
    llm = _action_llm(
        classifier_json("hack-and-slash", confidence=0.9),
        answer="You attack with your weapon.",
    )
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "move"
    assert result.reply.text == "You attack with your weapon."
    assert result.reply.move is not None
    assert result.reply.move.outcomes is HACK_AND_SLASH_MOVE.outcomes
    assert result.reply.move.url == "/moves/hack-and-slash/"
    assert result.reply.move.roll is None


def test_low_confidence_asks_one_clarifying_question() -> None:
    llm = _action_llm(
        classifier_json("hack-and-slash", confidence=0.4, alternatives=["defy-danger"])
    )
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "clarification"
    assert result.reply.text == (
        "I'm not sure which move this is. Do you mean Hack and Slash (when you "
        "attack an enemy in melee) or Defy Danger (when you act despite an "
        "imminent threat or suffer a calamity)? Tell me a bit more about what "
        "your character is trying to do."
    )
    assert not any(r.role == "answer" for r in llm.requests)
    assert "clarification_requested" in tracer.event_names()


@pytest.mark.parametrize(
    ("confidence", "expected_kind"), [(0.6, "move"), (0.59, "clarification")]
)
def test_clarification_threshold_boundary(
    confidence: float, expected_kind: str
) -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=confidence))
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == expected_kind


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (
            [],
            "I'm not sure which move this is. Tell me a bit more about what "
            "your character is trying to do.",
        ),
        (
            [HACK_AND_SLASH_MOVE],
            "I'm not sure this is Hack and Slash (when you attack an enemy in "
            "melee). Tell me a bit more about what your character is trying to "
            "do.",
        ),
        (
            [HACK_AND_SLASH_MOVE, DEFY_DANGER_MOVE],
            "I'm not sure which move this is. Do you mean Hack and Slash (when "
            "you attack an enemy in melee) or Defy Danger (when you act despite "
            "an imminent threat or suffer a calamity)? Tell me a bit more about "
            "what your character is trying to do.",
        ),
        (
            [HACK_AND_SLASH_MOVE, DEFY_DANGER_MOVE, "no_move"],
            "I'm not sure which move this is. Do you mean Hack and Slash (when "
            "you attack an enemy in melee), Defy Danger (when you act despite "
            "an imminent threat or suffer a calamity) or no move at all? Tell "
            "me a bit more about what your character is trying to do.",
        ),
    ],
)
def test_clarification_text_option_counts(
    options: list[Move | str], expected: str
) -> None:
    assert clarification_text(options) == expected


def test_clarification_truncates_to_three_options() -> None:
    llm = _action_llm(
        classifier_json(
            "hack-and-slash",
            confidence=0.3,
            alternatives=["defy-danger", "volley", "no_move"],
        )
    )
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "clarification"
    assert "Hack and Slash" in result.reply.text
    assert "Defy Danger" in result.reply.text
    assert "Volley" in result.reply.text
    assert "no move at all" not in result.reply.text


def test_no_move_is_first_class() -> None:
    llm = _action_llm(
        classifier_json(
            "no_move",
            confidence=0.9,
            rationale="Walking into town triggers nothing.",
        )
    )
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I walk into town")))

    assert result.reply.kind == "no_move"
    assert result.reply.text == (
        "No move is triggered. Walking into town triggers nothing."
    )
    assert result.reply.move is None
    assert not any(r.role == "answer" for r in llm.requests)


def test_low_confidence_no_move_clarifies() -> None:
    llm = _action_llm(classifier_json("no_move", confidence=0.3))
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I walk into town")))

    assert result.reply.kind == "clarification"


def test_unknown_move_id_forces_clarification() -> None:
    llm = _action_llm(
        classifier_json("backstab", confidence=0.95, alternatives=["hack-and-slash"])
    )
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I stab them in the back")))

    assert result.reply.kind == "clarification"
    assert result.classification is not None
    assert result.classification.move_id == "no_move"
    assert result.classification.confidence == 0.0
    unknown_events = [e for e in tracer.events if e.name == "classifier_unknown_move"]
    assert len(unknown_events) == 1
    assert unknown_events[0].attributes["move_id"] == "backstab"


def test_unknown_alternatives_stripped() -> None:
    llm = _action_llm(
        classifier_json(
            "hack-and-slash",
            confidence=0.9,
            alternatives=["volley", "nope", "volley", "hack-and-slash"],
        )
    )
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.classification is not None
    assert result.classification.alternatives == ("volley",)
    stripped_events = [
        e for e in tracer.events if e.name == "classifier_alternatives_stripped"
    ]
    assert len(stripped_events) == 1
    assert stripped_events[0].attributes["ids"] == "nope"


@pytest.mark.parametrize(
    (
        "move_id",
        "classifier_stat",
        "expected_roll_stat",
        "expect_overridden_event",
    ),
    [
        ("hack-and-slash", "DEX", "STR", True),
        ("defy-danger", "DEX", "DEX", False),
        ("defy-danger", None, None, False),
        ("last-breath", None, None, False),
        ("make-camp", None, None, False),
    ],
)
def test_roll_stat_resolution(
    move_id: str,
    classifier_stat: AbilityStat | None,
    expected_roll_stat: AbilityStat | None,
    expect_overridden_event: bool,
) -> None:
    llm = _action_llm(classifier_json(move_id, confidence=0.9, stat=classifier_stat))
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I do a thing")))

    assert result.classification is not None
    overridden_events = [
        e for e in tracer.events if e.name == "classifier_stat_overridden"
    ]
    if expect_overridden_event:
        assert len(overridden_events) == 1
        assert overridden_events[0].attributes["classifier_stat"] == classifier_stat
        assert overridden_events[0].attributes["move_stat"] == expected_roll_stat
    else:
        assert overridden_events == []
    if result.reply.kind == "move":
        assert result.reply.move is not None
        assert result.reply.move.roll_stat == expected_roll_stat
    if move_id == "make-camp":
        assert result.reply.move is not None
        assert result.reply.move.stat is None


def test_explain_request_parameters() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    assistant, _ = make_assistant(llm)

    asyncio.run(assistant.run(turn("I attack the orc")))

    request = next(r for r in llm.requests if r.role == "answer")
    assert request.role == "answer"
    assert request.max_tokens == 300
    assert "Hack and Slash" in request.user
    assert "When you attack an enemy in melee" in request.user
    assert "I attack the orc" in request.user
    assert "Roll: roll+STR" in request.user


@pytest.mark.parametrize(
    ("move", "roll_stat", "expected"),
    [
        (HACK_AND_SLASH_MOVE, "STR", "roll+STR"),
        (
            DEFY_DANGER_MOVE,
            None,
            "roll+the stat that matches how you act (DEX, CON, INT, WIS, STR or CHA)",
        ),
        (BOND_MOVE, None, "roll+Bond"),
        (LAST_BREATH_MOVE, None, "roll 2d6 with no stat added"),
        (MAKE_CAMP_MOVE, None, "not rolled"),
    ],
)
def test_roll_phrase_cases(
    move: Move, roll_stat: AbilityStat | None, expected: str
) -> None:
    assert roll_phrase(move, roll_stat) == expected


def test_rolled_move_without_ability_stat_is_explained_and_rolled() -> None:
    llm = _action_llm(classifier_json("last-breath", confidence=0.9))
    rng = ScriptedRandom([4, 4])
    assistant, _ = make_assistant(llm, rng=rng)

    result = asyncio.run(
        assistant.run(turn("I'm dying", roll_requested=True, modifier=0))
    )

    request = next(r for r in llm.requests if r.role == "answer")
    assert "Roll: roll 2d6 with no stat added" in request.user

    assert result.reply.move is not None
    assert result.reply.move.stat == "NONE"
    assert result.reply.move.roll_stat is None
    assert result.reply.move.outcome is not None
    assert result.reply.move.outcome.band == "weak_hit"
    assert result.reply.text.endswith("Rolled 4 + 4 + 0 = 8: 7-9.")


def test_explain_port_error_returns_error() -> None:
    llm = _action_llm(
        classifier_json("hack-and-slash", confidence=0.9),
        answer=PortError("timeout"),
    )
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "error"
    port_error_events = [e for e in tracer.events if e.name == "port_error"]
    assert len(port_error_events) == 1
    assert port_error_events[0].attributes["port"] == "llm"


def test_classifier_port_error_returns_error() -> None:
    llm = _action_llm(PortError("timeout"))
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "error"
    assert not any(r.role == "answer" for r in llm.requests)


def test_empty_explanation_returns_error() -> None:
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9), answer="   ")
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "error"
    assert "llm_output_invalid" in tracer.event_names()


def test_classifier_invalid_output_returns_error() -> None:
    llm = _action_llm("{}")
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "error"


def test_action_with_rules_question_prefers_move_branch() -> None:
    message = "I swing at the orc, does armor reduce damage?"
    llm = _action_llm(classifier_json("hack-and-slash", confidence=0.9))
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn(message)))

    assert result.reply.kind == "move"
    request = next(r for r in llm.requests if r.role == "answer")
    assert message in request.user
