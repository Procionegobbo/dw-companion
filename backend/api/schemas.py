"""The chat request schema, the shared reply-payload builder, and `ApiError`
(spec 008 Data Model: Backend types, Wire contract).

`reply_payload` never re-derives anything the graph already decided (D18): it only
reshapes `TurnResult` into the exact JSON the wire contract and the contract fixture
describe, in the documented key order.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.dice import Roll
from backend.domain.outcome import Outcome
from backend.domain.rulebook import Outcomes
from backend.graph.state import Citation, MoveCard, TurnResult

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str
    roll: bool = False
    modifier: int | None = Field(default=None, ge=-10, le=10)
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class ApiError(Exception):
    """Carries everything the `/api/chat` exception handler needs (D3, D8).

    Never includes exception text in the response: `message` is always
    server-authored copy from `backend/api/messages.py`.
    """

    def __init__(
        self, status: int, code: str, message: str, retry_after_s: int | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after_s = retry_after_s


def _citation_payload(citation: Citation) -> JsonValue:
    payload: dict[str, JsonValue] = {
        "section_id": citation.section_id,
        "title": citation.title,
        "url": citation.url,
    }
    return payload


def _outcomes_payload(outcomes: Outcomes | None) -> JsonValue:
    if outcomes is None:
        return None
    payload: dict[str, JsonValue] = {
        "strong_hit": outcomes.strong_hit,
        "weak_hit": outcomes.weak_hit,
        "miss": outcomes.miss,
    }
    return payload


def _roll_payload(roll: Roll | None) -> JsonValue:
    if roll is None:
        return None
    dice: list[JsonValue] = [roll.dice[0], roll.dice[1]]
    payload: dict[str, JsonValue] = {
        "dice": dice,
        "modifier": roll.modifier,
        "total": roll.total,
    }
    return payload


def _outcome_payload(outcome: Outcome | None) -> JsonValue:
    if outcome is None:
        return None
    payload: dict[str, JsonValue] = {"band": outcome.band, "text": outcome.text}
    return payload


def _band_entry(modifier: int, band: str) -> JsonValue:
    payload: dict[str, JsonValue] = {"modifier": modifier, "band": band}
    return payload


def _move_payload(move: MoveCard | None) -> JsonValue:
    if move is None:
        return None
    bands_by_modifier: list[JsonValue] = [
        _band_entry(modifier, band) for modifier, band in move.bands_by_modifier
    ]
    payload: dict[str, JsonValue] = {
        "move_id": move.move_id,
        "name": move.name,
        "url": move.url,
        "trigger": move.trigger,
        "stat": move.stat,
        "roll_stat": move.roll_stat,
        "outcomes": _outcomes_payload(move.outcomes),
        "roll": _roll_payload(move.roll),
        "outcome": _outcome_payload(move.outcome),
        "bands_by_modifier": bands_by_modifier,
    }
    return payload


def reply_payload(result: TurnResult, trace_id: str) -> dict[str, JsonValue]:
    reply = result.reply
    citations: list[JsonValue] = [
        _citation_payload(citation) for citation in reply.citations
    ]
    return {
        "trace_id": trace_id,
        "kind": reply.kind,
        "text": reply.text,
        "citations": citations,
        "move": _move_payload(reply.move),
    }
