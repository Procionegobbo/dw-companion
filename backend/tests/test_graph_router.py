"""Tests for the `router` node, the `out_of_scope` path and routing into the move
branch (spec 006 Testing).
"""

from __future__ import annotations

import asyncio

from backend.graph.replies import ERROR_TEXT, OUT_OF_SCOPE_TEXT
from backend.graph.state import Reply
from backend.ports.errors import PortError
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import (
    chunk,
    classifier_json,
    make_assistant,
    router_json,
    turn,
)


def test_out_of_scope_reply_without_further_calls() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    retriever = FakeRetriever()
    assistant, _ = make_assistant(llm, retriever=retriever)

    result = asyncio.run(assistant.run(turn()))

    assert result.reply == Reply(kind="out_of_scope", text=OUT_OF_SCOPE_TEXT)
    assert len(llm.requests) == 1
    assert llm.requests[0].role == "router"
    assert retriever.calls == []
    assert result.classification is None


def test_router_request_parameters() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    assistant, _ = make_assistant(llm)

    asyncio.run(assistant.run(turn(message="How does Hold work?")))

    request = llm.requests[0]
    assert request.role == "router"
    assert request.temperature == 0.0
    assert request.max_tokens == 100
    assert request.schema_name == "router_decision"
    assert "<user_message>" in request.user
    assert "How does Hold work?" in request.user


def test_router_invalid_output_returns_error() -> None:
    llm = FakeLLMClient({"router": ["not json"]})
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "error"
    assert result.reply.text == ERROR_TEXT
    assert "llm_output_invalid" in tracer.event_names()
    assert result.intent is None


def test_router_port_error_returns_error() -> None:
    llm = FakeLLMClient({"router": [PortError("timeout")]})
    assistant, tracer = make_assistant(llm)

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "error"
    port_error_events = [event for event in tracer.events if event.name == "port_error"]
    assert len(port_error_events) == 1
    assert port_error_events[0].attributes["port"] == "llm"


def test_routes_rules_question_to_rules_branch() -> None:
    chunks = [chunk("moves/hack-and-slash", title="Hack and Slash")]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage [[moves/hack-and-slash]]."],
        }
    )
    retriever = FakeRetriever(chunks)
    assistant, _ = make_assistant(llm, retriever=retriever)

    result = asyncio.run(assistant.run(turn("How does Hack and Slash work?")))

    assert retriever.calls == [("How does Hack and Slash work?", 6)]
    assert result.reply.kind == "rules_answer"


def test_routes_action_to_move_branch() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash")],
            "answer": ["Explanation."],
        }
    )
    retriever = FakeRetriever()
    assistant, _ = make_assistant(llm, retriever=retriever)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert any(r.role == "classifier" for r in llm.requests)
    assert retriever.calls == []
    assert result.reply.kind == "move"


def test_low_router_confidence_does_not_branch() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description", confidence=0.42)],
            "classifier": [classifier_json("hack-and-slash", confidence=0.9)],
            "answer": ["Explanation."],
        }
    )
    assistant, _ = make_assistant(llm)

    result = asyncio.run(assistant.run(turn("I attack the orc")))

    assert result.reply.kind == "move"
    assert result.router_confidence == 0.42
    assert result.intent == "action_description"
