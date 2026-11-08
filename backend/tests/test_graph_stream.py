"""Tests for `Assistant.stream` (spec 008 Testing).

The five setups below mirror `test_graph_tracing.py`'s per-path scripted fakes
(out_of_scope, rules, clarify, no_move, move+roll), so the expected node lists are
spec 006's own traced node lists for those paths.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping

import pytest

# `_assistant_from_compiled` is the documented test seam for the no-reply guard
# (spec 006 Data Model), reused here for the streaming variant of that guard.
from backend.graph.builder import (
    Assistant,
    _assistant_from_compiled,  # pyright: ignore[reportPrivateUsage]
)
from backend.graph.state import AssistantEvent, NodeCompleted, TurnInput, TurnResult
from backend.ports.errors import PortError
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


_PATHS: list[tuple[Callable[[], _Setup], list[str]]] = [
    (_out_of_scope_setup, ["router", "out_of_scope"]),
    (
        _rules_setup,
        ["router", "retrieve", "answer_with_citations", "citation_validator"],
    ),
    (_clarify_setup, ["router", "classify_move", "clarify"]),
    (_no_move_setup, ["router", "classify_move", "no_move"]),
    (_move_with_roll_setup, ["router", "classify_move", "explain", "roll", "outcome"]),
]
_PATH_IDS = ["out_of_scope", "rules", "clarify", "no_move", "move_with_roll"]


async def _collect(assistant: Assistant, turn_input: TurnInput) -> list[AssistantEvent]:
    events: list[AssistantEvent] = []
    async for event in assistant.stream(turn_input):
        events.append(event)
    return events


@pytest.mark.parametrize(("setup", "expected_nodes"), _PATHS, ids=_PATH_IDS)
def test_stream_yields_nodes_then_result(
    setup: Callable[[], _Setup], expected_nodes: list[str]
) -> None:
    llm, retriever, rng, turn_input = setup()
    assistant, _tracer = make_assistant(llm, retriever=retriever, rng=rng)

    events = asyncio.run(_collect(assistant, turn_input))

    node_events = events[:-1]
    assert all(isinstance(e, NodeCompleted) for e in node_events)
    assert [e.node for e in node_events if isinstance(e, NodeCompleted)] == (
        expected_nodes
    )
    final = events[-1]
    assert isinstance(final, TurnResult)
    assert sum(isinstance(e, TurnResult) for e in events) == 1


@pytest.mark.parametrize(("setup", "_expected_nodes"), _PATHS, ids=_PATH_IDS)
def test_stream_result_equals_run_result(
    setup: Callable[[], _Setup], _expected_nodes: list[str]
) -> None:
    run_llm, run_retriever, run_rng, turn_input = setup()
    run_assistant, _ = make_assistant(run_llm, retriever=run_retriever, rng=run_rng)
    run_result = asyncio.run(run_assistant.run(turn_input))

    stream_llm, stream_retriever, stream_rng, _ = setup()
    stream_assistant, _ = make_assistant(
        stream_llm, retriever=stream_retriever, rng=stream_rng
    )
    events = asyncio.run(_collect(stream_assistant, turn_input))

    assert events[-1] == run_result


def test_stream_error_reply_still_completes() -> None:
    llm = FakeLLMClient({"router": [PortError("down")]})
    assistant, _tracer = make_assistant(llm)

    events = asyncio.run(_collect(assistant, turn()))

    assert events[0] == NodeCompleted("router")
    final = events[-1]
    assert isinstance(final, TurnResult)
    assert final.reply.kind == "error"
    assert len(events) == 2


class _NoReplyGraph:
    """A minimal stand-in compiled graph whose stream never produces a reply.

    Mirrors `test_graph_inputs.py`'s `_SingleNodeGraph`, extended with `astream`
    so the streaming no-reply guard can be exercised without `langgraph` (D2).
    """

    async def astream(
        self, state: Mapping[str, object], /, *, stream_mode: object
    ) -> AsyncIterator[tuple[str, object]]:
        yield ("values", {})


def test_stream_without_reply_raises() -> None:
    assistant = _assistant_from_compiled(_NoReplyGraph())

    async def _run() -> None:
        async for _event in assistant.stream(turn()):
            pass

    with pytest.raises(RuntimeError, match="graph finished without a reply"):
        asyncio.run(_run())


def test_node_completed_validation() -> None:
    with pytest.raises(ValueError, match="node"):
        NodeCompleted("")
