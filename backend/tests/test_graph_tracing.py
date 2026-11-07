"""Tests for tracing (spec 006 Testing: out-of-scope, rules and move paths)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable

import pytest

from backend.graph.state import TurnInput
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import (
    chunk,
    classifier_json,
    make_assistant,
    router_json,
    turn,
)

_Setup = tuple[FakeLLMClient, FakeRetriever, ScriptedRandom, TurnInput]


def _out_of_scope_setup() -> _Setup:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    return llm, FakeRetriever(), ScriptedRandom([]), turn()


def _rules_setup() -> _Setup:
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage [[moves/hack-and-slash]]."],
        }
    )
    retriever = FakeRetriever([chunk("moves/hack-and-slash")])
    return llm, retriever, ScriptedRandom([]), turn()


def _clarify_setup() -> _Setup:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash", confidence=0.4)],
        }
    )
    return llm, FakeRetriever(), ScriptedRandom([]), turn()


def _no_move_setup() -> _Setup:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("no_move", confidence=0.9)],
        }
    )
    return llm, FakeRetriever(), ScriptedRandom([]), turn()


def _move_with_roll_setup() -> _Setup:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash", confidence=0.9)],
            "answer": ["Explanation."],
        }
    )
    roll_turn = turn("I attack the orc", roll_requested=True, modifier=1)
    return llm, FakeRetriever(), ScriptedRandom([4, 5]), roll_turn


@pytest.mark.parametrize(
    ("setup", "expected_nodes"),
    [
        (_out_of_scope_setup, ["router", "out_of_scope"]),
        (
            _rules_setup,
            ["router", "retrieve", "answer_with_citations", "citation_validator"],
        ),
        (_clarify_setup, ["router", "classify_move", "clarify"]),
        (_no_move_setup, ["router", "classify_move", "no_move"]),
        (
            _move_with_roll_setup,
            ["router", "classify_move", "explain", "roll", "outcome"],
        ),
    ],
    ids=["out_of_scope", "rules", "clarify", "no_move", "move_with_roll"],
)
def test_every_executed_node_is_traced(
    setup: Callable[[], _Setup],
    expected_nodes: list[str],
) -> None:
    llm, retriever, rng, turn_input = setup()
    assistant, tracer = make_assistant(llm, retriever=retriever, rng=rng)

    asyncio.run(assistant.run(turn_input))

    assert [node.node for node in tracer.nodes] == expected_nodes


def test_generation_traced_per_llm_call() -> None:
    llm, retriever, _, turn_input = _rules_setup()
    assistant, tracer = make_assistant(llm, retriever=retriever)

    asyncio.run(assistant.run(turn_input))

    assert len(tracer.generations) == 2
    assert [g.request.role for g in tracer.generations] == ["router", "answer"]
    assert [g.response.model for g in tracer.generations] == [
        "fake-router",
        "fake-answer",
    ]
    for generation in tracer.generations:
        assert generation.response.input_tokens == 10
        assert generation.response.output_tokens == 5


def test_router_node_attributes() -> None:
    llm, retriever, _, turn_input = _rules_setup()
    assistant, tracer = make_assistant(llm, retriever=retriever)

    asyncio.run(assistant.run(turn_input))

    router_trace = next(node for node in tracer.nodes if node.node == "router")
    assert router_trace.attributes == {"intent": "rules_question", "confidence": 0.9}


def test_trace_ids_propagate() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    assistant, tracer = make_assistant(llm)

    asyncio.run(assistant.run(turn()))

    assert tracer.nodes, "expected at least one recorded node trace"
    assert tracer.generations, "expected at least one recorded generation trace"
    assert tracer.events == [], "the out-of-scope path should not emit events"

    for node_trace in tracer.nodes:
        assert node_trace.trace_id == "t1"
        assert node_trace.session_id == "s1"
    for generation in tracer.generations:
        assert generation.trace_id == "t1"
        assert generation.session_id == "s1"
    for event in tracer.events:
        assert event.trace_id == "t1"
        assert event.session_id == "s1"


def test_latency_from_injected_clock() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    assistant, tracer = make_assistant(llm)

    asyncio.run(assistant.run(turn()))

    out_of_scope_trace = next(
        node for node in tracer.nodes if node.node == "out_of_scope"
    )
    assert out_of_scope_trace.latency_ms == pytest.approx(10.0)
    for node_trace in tracer.nodes:
        assert math.isfinite(node_trace.latency_ms)
        assert node_trace.latency_ms > 0


def test_error_node_traced() -> None:
    llm = FakeLLMClient({"router": ["not json"]})
    assistant, tracer = make_assistant(llm)

    asyncio.run(assistant.run(turn()))

    router_trace = next(node for node in tracer.nodes if node.node == "router")
    assert router_trace.attributes == {"error": True}
