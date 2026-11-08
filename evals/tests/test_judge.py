"""Tests for `evals/judge.py`: the key-fact LLM judge."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from backend.ports.errors import PortError
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.tracer import FakeTracer
from evals.budget import generation_cost
from evals.judge import (
    JUDGE_MAX_TOKENS,
    JUDGE_NODE,
    JudgeError,
    judge_key_facts,
    judge_request,
    parse_judge_output,
)

from .helpers import CostingLLMClient


def _clock() -> Callable[[], float]:
    calls = {"n": 0}

    def clock() -> float:
        calls["n"] += 1
        return calls["n"] * 0.01

    return clock


def _verdicts_json(entries: list[tuple[int, object, str]]) -> str:
    return json.dumps(
        {
            "facts": [
                {"index": index, "present": present, "evidence": evidence}
                for index, present, evidence in entries
            ]
        }
    )


def test_judge_request_shape() -> None:
    request = judge_request(
        "What happens on Last Breath?", "You roll 2d6.", ["fact a", "fact b"]
    )
    assert request.role == "answer"
    assert request.schema_name == "key_fact_verdicts"
    assert request.temperature == 0.0
    assert request.max_tokens == JUDGE_MAX_TOKENS
    assert request.user == (
        "<question>\nWhat happens on Last Breath?\n</question>\n"
        "<answer>\nYou roll 2d6.\n</answer>\n"
        "<key_facts>\n0. fact a\n1. fact b\n</key_facts>"
    )


def test_parse_judge_output_valid() -> None:
    text = _verdicts_json([(1, True, "b evidence"), (0, False, "")])
    result = parse_judge_output(text, 2)
    assert result == ((False, ""), (True, "b evidence"))


_INVALID_CASES: tuple[tuple[str, str, str], ...] = (
    ("not JSON", "not json", "not valid JSON"),
    ("missing an index", _verdicts_json([(0, True, "x")]), "missing index"),
    (
        "a duplicate index",
        _verdicts_json([(0, True, "x"), (0, False, ""), (1, False, "")]),
        "duplicate index",
    ),
    (
        "an out-of-range index",
        _verdicts_json([(0, True, "x"), (2, False, "")]),
        "out of range",
    ),
    (
        "present: 1",
        _verdicts_json([(0, 1, "x"), (1, False, "")]),
        "present must be a boolean",
    ),
)


@pytest.mark.parametrize(
    ("label", "text", "match"),
    _INVALID_CASES,
    ids=[case[0] for case in _INVALID_CASES],
)
def test_parse_judge_output_invalid(label: str, text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_judge_output(text, 2)


def test_judge_records_generation_in_case_trace() -> None:
    tracer = FakeTracer()
    judge = FakeLLMClient({"answer": [_verdicts_json([(0, True, "e")])]})

    result = asyncio.run(
        judge_key_facts(
            judge,
            tracer,
            _clock(),
            trace_id="trace-1",
            session_id="run-1",
            question="q",
            answer="a",
            key_facts=["fact 0"],
        )
    )

    assert result[0].present is True
    assert len(tracer.generations) == 1
    generation = tracer.generations[0]
    assert generation.node == JUDGE_NODE
    assert generation.trace_id == "trace-1"


def test_judge_port_error_becomes_judge_error() -> None:
    tracer = FakeTracer()
    judge = FakeLLMClient({"answer": [PortError("boom")]})

    with pytest.raises(JudgeError):
        asyncio.run(
            judge_key_facts(
                judge,
                tracer,
                _clock(),
                trace_id="trace-1",
                session_id="run-1",
                question="q",
                answer="a",
                key_facts=["fact 0"],
            )
        )
    assert tracer.generations == []


def test_judge_invalid_output_still_recorded() -> None:
    tracer = FakeTracer()
    inner = FakeLLMClient({"answer": ["not json"]})
    judge = CostingLLMClient(inner, cost=0.002)

    with pytest.raises(JudgeError):
        asyncio.run(
            judge_key_facts(
                judge,
                tracer,
                _clock(),
                trace_id="trace-1",
                session_id="run-1",
                question="q",
                answer="a",
                key_facts=["fact 0"],
            )
        )

    assert len(tracer.generations) == 1
    generation = tracer.generations[0]
    assert generation.node == JUDGE_NODE
    assert generation_cost(generation) == (0.002, False)
