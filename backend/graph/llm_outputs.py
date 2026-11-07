"""Structured LLM output types, JSON Schemas and deterministic parsers (D4, D5).

Required keys must be present with the right types and ranges; extra keys are
ignored; any violation is an *invalid output* and raises `ValueError` (D5, no
retries).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast, get_args

from backend.domain.rulebook import ABILITY_STATS, AbilityStat

Intent = Literal["rules_question", "action_description", "out_of_scope"]
INTENTS: tuple[Intent, ...] = get_args(Intent)

NO_MOVE: Final = "no_move"


def _validate_confidence(value: object, *, type_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {type_name}: confidence must be a number")
    confidence = float(value)
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"invalid {type_name}: confidence must be between 0 and 1")
    return confidence


@dataclass(frozen=True, slots=True)
class RouterDecision:
    intent: Intent
    confidence: float

    def __post_init__(self) -> None:
        if self.intent not in INTENTS:
            raise ValueError(f"invalid RouterDecision: intent must be one of {INTENTS}")
        _validate_confidence(self.confidence, type_name="RouterDecision")


@dataclass(frozen=True, slots=True)
class MoveClassification:
    move_id: str
    confidence: float
    stat: AbilityStat | None
    rationale: str
    alternatives: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.move_id.strip():
            raise ValueError("invalid MoveClassification: move_id must be non-empty")
        _validate_confidence(self.confidence, type_name="MoveClassification")
        if self.stat is not None and self.stat not in ABILITY_STATS:
            raise ValueError(
                f"invalid MoveClassification: stat must be one of {ABILITY_STATS} "
                "or null"
            )


def router_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent", "confidence"],
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def parse_router_output(text: str) -> RouterDecision:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid router output: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError("invalid router output: expected a JSON object")
    data = cast(dict[str, object], raw)

    intent_raw = data.get("intent")
    if not isinstance(intent_raw, str) or intent_raw not in INTENTS:
        raise ValueError(f"invalid router output: intent must be one of {INTENTS}")

    if "confidence" not in data:
        raise ValueError("invalid router output: confidence is required")
    confidence_raw = data["confidence"]
    if isinstance(confidence_raw, bool) or not isinstance(confidence_raw, (int, float)):
        raise ValueError("invalid router output: confidence must be a number")

    return RouterDecision(intent=intent_raw, confidence=float(confidence_raw))


def classifier_schema(candidate_ids: Sequence[str]) -> dict[str, object]:
    enum_values: list[str] = [*candidate_ids, NO_MOVE]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["move_id", "confidence", "stat", "rationale", "alternatives"],
        "properties": {
            "move_id": {"type": "string", "enum": enum_values},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "stat": {
                "type": ["string", "null"],
                "enum": [*ABILITY_STATS, None],
            },
            "rationale": {"type": "string"},
            "alternatives": {
                "type": "array",
                "items": {"type": "string", "enum": enum_values},
            },
        },
    }


def parse_classifier_output(text: str) -> MoveClassification:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid classifier output: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError("invalid classifier output: expected a JSON object")
    data = cast(dict[str, object], raw)

    move_id_raw = data.get("move_id")
    if not isinstance(move_id_raw, str) or not move_id_raw.strip():
        raise ValueError(
            "invalid classifier output: move_id must be a non-empty string"
        )

    if "confidence" not in data:
        raise ValueError("invalid classifier output: confidence is required")
    confidence_raw = data["confidence"]
    if isinstance(confidence_raw, bool) or not isinstance(confidence_raw, (int, float)):
        raise ValueError("invalid classifier output: confidence must be a number")

    if "stat" not in data:
        raise ValueError("invalid classifier output: stat is required")
    stat_raw = data["stat"]
    stat: AbilityStat | None
    if stat_raw is None:
        stat = None
    elif isinstance(stat_raw, str) and stat_raw in ABILITY_STATS:
        stat = stat_raw
    else:
        raise ValueError(
            f"invalid classifier output: stat must be one of {ABILITY_STATS} or null"
        )

    if "rationale" not in data:
        raise ValueError("invalid classifier output: rationale is required")
    rationale_raw = data["rationale"]
    if not isinstance(rationale_raw, str):
        raise ValueError("invalid classifier output: rationale must be a string")

    if "alternatives" not in data:
        raise ValueError("invalid classifier output: alternatives is required")
    alternatives_raw = data["alternatives"]
    if not isinstance(alternatives_raw, list):
        raise ValueError(
            "invalid classifier output: alternatives must be a list of strings"
        )
    alternatives_items = cast("list[object]", alternatives_raw)
    if not all(isinstance(item, str) for item in alternatives_items):
        raise ValueError(
            "invalid classifier output: alternatives must be a list of strings"
        )
    alternatives = cast("list[str]", alternatives_items)

    return MoveClassification(
        move_id=move_id_raw,
        confidence=float(confidence_raw),
        stat=stat,
        rationale=rationale_raw,
        alternatives=tuple(alternatives),
    )
