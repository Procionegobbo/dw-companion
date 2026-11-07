"""Tests for router and classifier structured output (spec 006 Testing)."""

from __future__ import annotations

from typing import cast

import pytest

from backend.graph.llm_outputs import (
    Intent,
    classifier_schema,
    parse_classifier_output,
    parse_router_output,
    router_schema,
)


@pytest.mark.parametrize(
    "intent", ["rules_question", "action_description", "out_of_scope"]
)
def test_parse_router_output_valid(intent: Intent) -> None:
    decision = parse_router_output(f'{{"intent": "{intent}", "confidence": 0.75}}')
    assert decision.intent == intent
    assert decision.confidence == 0.75


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("not json", "not valid JSON"),
        ("[]", "expected a JSON object"),
        ('{"intent": "rules_question"}', "confidence"),
        ('{"intent": "chitchat", "confidence": 0.5}', "intent"),
        ('{"intent": "rules_question", "confidence": 1.2}', "confidence"),
        ('{"intent": "rules_question", "confidence": true}', "confidence"),
    ],
)
def test_parse_router_output_invalid(text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_router_output(text)


def test_parse_router_ignores_extra_keys() -> None:
    decision = parse_router_output(
        '{"intent": "out_of_scope", "confidence": 0.5, "note": "ignored"}'
    )
    assert decision.intent == "out_of_scope"
    assert decision.confidence == 0.5


def test_router_schema_shape() -> None:
    schema = router_schema()
    assert schema["required"] == ["intent", "confidence"]
    assert schema["additionalProperties"] is False
    assert schema["properties"] == {
        "intent": {
            "type": "string",
            "enum": ["rules_question", "action_description", "out_of_scope"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }


def test_parse_classifier_output_valid() -> None:
    classification = parse_classifier_output(
        '{"move_id": "hack-and-slash", "confidence": 0.9, "stat": "DEX", '
        '"rationale": "r", "alternatives": ["volley"]}'
    )
    assert classification.move_id == "hack-and-slash"
    assert classification.confidence == 0.9
    assert classification.stat == "DEX"
    assert classification.rationale == "r"
    assert classification.alternatives == ("volley",)

    null_stat = parse_classifier_output(
        '{"move_id": "no_move", "confidence": 0.5, "stat": null, '
        '"rationale": "walking triggers nothing", "alternatives": []}'
    )
    assert null_stat.move_id == "no_move"
    assert null_stat.stat is None


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (
            '{"move_id": "hack-and-slash", "confidence": 0.5, "stat": "BOND", '
            '"rationale": "r", "alternatives": []}',
            "stat",
        ),
        (
            '{"move_id": "hack-and-slash", "confidence": 0.5, "stat": "VARIES", '
            '"rationale": "r", "alternatives": []}',
            "stat",
        ),
        (
            '{"move_id": "hack-and-slash", "confidence": 0.5, "stat": null, '
            '"rationale": "r", "alternatives": "x"}',
            "alternatives",
        ),
        (
            '{"move_id": "hack-and-slash", "confidence": 0.5, "stat": null, '
            '"alternatives": []}',
            "rationale",
        ),
        (
            '{"move_id": "", "confidence": 0.5, "stat": null, "rationale": "r", '
            '"alternatives": []}',
            "move_id",
        ),
        (
            '{"move_id": "hack-and-slash", "confidence": -0.1, "stat": null, '
            '"rationale": "r", "alternatives": []}',
            "confidence",
        ),
    ],
)
def test_parse_classifier_output_invalid(text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_classifier_output(text)


def test_classifier_schema_enumerates_candidates() -> None:
    schema = classifier_schema(["hack-and-slash", "volley"])
    properties = cast(dict[str, object], schema["properties"])
    move_id_schema = cast(dict[str, object], properties["move_id"])
    alternatives_schema = cast(dict[str, object], properties["alternatives"])
    items_schema = cast(dict[str, object], alternatives_schema["items"])

    assert move_id_schema["enum"] == ["hack-and-slash", "volley", "no_move"]
    assert items_schema["enum"] == ["hack-and-slash", "volley", "no_move"]
