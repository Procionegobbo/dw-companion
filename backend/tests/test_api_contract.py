"""Tests for `backend/api/schemas.py`'s `reply_payload` against the shared
contract fixture (spec 008 D18, Testing)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest

from backend.api.schemas import reply_payload
from backend.domain.dice import Band, Roll
from backend.domain.outcome import Outcome
from backend.domain.rulebook import Outcomes
from backend.domain.urls import move_url, section_url
from backend.graph.state import Citation, MoveCard, Reply, ReplyKind, TurnResult

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "chat_reply_examples.json"
FIXTURE: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _result_for(key: str) -> TurnResult:
    if key == "rules_answer":
        reply = Reply(
            kind="rules_answer",
            text=(
                "Deal your damage [[moves/hack-and-slash]].\n\nTo avoid a blow, "
                "Defy Danger [[moves/defy-danger]]."
            ),
            citations=(
                Citation(
                    "moves/hack-and-slash",
                    "Hack and Slash",
                    "/rules/moves/hack-and-slash/",
                ),
                Citation(
                    "moves/defy-danger", "Defy Danger", "/rules/moves/defy-danger/"
                ),
            ),
        )
    elif key == "rules_not_found":
        reply = Reply(
            kind="rules_not_found",
            text="I couldn't find this in the rules.",
            citations=(
                Citation(
                    "moves/last-breath", "Last Breath", "/rules/moves/last-breath/"
                ),
            ),
        )
    elif key == "move_rolled_with_modifier":
        outcomes = Outcomes(
            strong_hit="On a 10+ you deal your damage.",
            weak_hit="On a 7-9 you deal your damage and the enemy attacks you.",
            miss=None,
        )
        roll = Roll(dice=(4, 5), modifier=1)
        outcome = Outcome(
            move_id="hack-and-slash",
            roll=roll,
            band="strong_hit",
            text="On a 10+ you deal your damage.",
        )
        move = MoveCard(
            move_id="hack-and-slash",
            name="Hack and Slash",
            url=move_url("hack-and-slash"),
            trigger="When you attack an enemy in melee",
            stat="STR",
            roll_stat="STR",
            outcomes=outcomes,
            roll=roll,
            outcome=outcome,
        )
        reply = Reply(
            kind="move",
            text=(
                "Attacking the goblin in melee triggers Hack and Slash.\n\n"
                "Rolled 4 + 5 + 1 = 10: 10+."
            ),
            move=move,
        )
    elif key == "move_rolled_without_modifier":
        outcomes = Outcomes(
            strong_hit="On a 10+, you do what you set out to.",
            weak_hit="On a 7-9, you stumble or hesitate.",
            miss=None,
        )
        roll = Roll(dice=(3, 5), modifier=None)
        bands: tuple[tuple[int, Band], ...] = (
            (-3, "miss"),
            (-2, "miss"),
            (-1, "weak_hit"),
            (0, "weak_hit"),
            (1, "weak_hit"),
            (2, "strong_hit"),
            (3, "strong_hit"),
        )
        move = MoveCard(
            move_id="defy-danger",
            name="Defy Danger",
            url=move_url("defy-danger"),
            trigger="When you act despite an imminent threat",
            stat="VARIES",
            roll_stat=None,
            outcomes=outcomes,
            roll=roll,
            bands_by_modifier=bands,
        )
        reply = Reply(
            kind="move",
            text=(
                "Leaping the chasm under fire triggers Defy Danger.\n\nRolled 3 + 5 "
                "= 8. Add your modifier: -3 to -2: 6-; -1 to +1: 7-9; +2 to +3: 10+."
            ),
            move=move,
        )
    else:
        raise AssertionError(f"unknown fixture key {key!r}")

    return TurnResult(
        reply=reply,
        intent=None,
        router_confidence=None,
        classification=None,
        retrieved_section_ids=(),
    )


@pytest.mark.parametrize("key", sorted(FIXTURE))
def test_reply_payload_matches_fixture(key: str) -> None:
    expected = FIXTURE[key]

    payload = reply_payload(_result_for(key), expected["trace_id"])

    assert payload == expected
    assert list(payload) == list(expected)


def test_fixture_urls_follow_url_contract() -> None:
    for entry in FIXTURE.values():
        for citation in entry["citations"]:
            assert citation["url"] == section_url(citation["section_id"])
        if entry["move"] is not None:
            assert entry["move"]["url"] == move_url(entry["move"]["move_id"])


def test_reply_payload_is_json_serialisable_for_every_kind() -> None:
    for kind in get_args(ReplyKind):
        result = TurnResult(
            reply=Reply(kind=kind, text="t"),
            intent=None,
            router_confidence=None,
            classification=None,
            retrieved_section_ids=(),
        )

        json.dumps(reply_payload(result, "t" * 32))
