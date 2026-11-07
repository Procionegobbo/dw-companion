"""Tests for the rules branch: `retrieve`, `answer_with_citations` and
`citation_validator` (spec 006 Testing).
"""

from __future__ import annotations

import asyncio

from backend.graph.replies import NOT_FOUND_TEXT
from backend.graph.state import Citation
from backend.ports.errors import PortError
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import chunk, make_assistant, router_json, turn


def test_answer_with_valid_citations() -> None:
    chunks = [
        chunk("moves/hack-and-slash", title="Hack and Slash"),
        chunk("moves/defy-danger", title="Defy Danger"),
    ]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage [[moves/hack-and-slash]]."],
        }
    )
    assistant, _ = make_assistant(llm, retriever=FakeRetriever(chunks))

    result = asyncio.run(assistant.run(turn("How does Hack and Slash work?")))

    assert result.reply.kind == "rules_answer"
    assert result.reply.citations == (
        Citation(
            "moves/hack-and-slash", "Hack and Slash", "/rules/moves/hack-and-slash/"
        ),
    )
    assert result.retrieved_section_ids == ("moves/hack-and-slash", "moves/defy-danger")


def test_invalid_citation_stripped_and_traced() -> None:
    chunks = [chunk("moves/hack-and-slash", title="Hack and Slash")]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": [
                "Deal damage [[moves/hack-and-slash]]. Also see [[moves/unknown]]."
            ],
        }
    )
    assistant, tracer = make_assistant(llm, retriever=FakeRetriever(chunks))

    result = asyncio.run(assistant.run(turn()))

    assert "[[moves/unknown]]" not in result.reply.text
    stripped_events = [e for e in tracer.events if e.name == "citations_stripped"]
    assert len(stripped_events) == 1
    assert stripped_events[0].attributes["ids"] == "moves/unknown"
    assert stripped_events[0].attributes["count"] == 1


def test_no_valid_citation_returns_not_found_with_closest_sections() -> None:
    chunks = [chunk(f"s/section-{i}", title=f"Section {i}") for i in range(5)]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["See [[s/unknown]] for details."],
        }
    )
    assistant, tracer = make_assistant(llm, retriever=FakeRetriever(chunks))

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "rules_not_found"
    assert result.reply.text == NOT_FOUND_TEXT
    assert result.reply.citations == tuple(
        Citation(c.section_id, c.title, c.anchor_url) for c in chunks[:3]
    )
    assert "no_valid_citation" in tracer.event_names()


def test_answer_without_citations_returns_not_found() -> None:
    chunks = [chunk("moves/hack-and-slash")]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["This is a plain answer with no markers."],
        }
    )
    assistant, _ = make_assistant(llm, retriever=FakeRetriever(chunks))

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "rules_not_found"
    assert result.reply.text == NOT_FOUND_TEXT


def test_empty_retrieval_skips_answer_llm() -> None:
    llm = FakeLLMClient({"router": [router_json("rules_question")]})
    assistant, _ = make_assistant(llm, retriever=FakeRetriever())

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "rules_not_found"
    assert result.reply.citations == ()
    assert len(llm.requests) == 1
    assert llm.requests[0].role == "router"


def test_answer_prompt_contains_retrieved_sections() -> None:
    chunks = [chunk("moves/hack-and-slash", title="Hack and Slash")]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage [[moves/hack-and-slash]]."],
        }
    )
    assistant, _ = make_assistant(llm, retriever=FakeRetriever(chunks))

    asyncio.run(assistant.run(turn()))

    request = llm.requests[1]
    assert request.role == "answer"
    assert request.max_tokens == 700
    assert request.response_schema is None
    assert request.schema_name is None
    assert "[[moves/hack-and-slash]] Hack and Slash" in request.user


def test_retriever_port_error_returns_error() -> None:
    llm = FakeLLMClient({"router": [router_json("rules_question")]})
    assistant, tracer = make_assistant(
        llm, retriever=FakeRetriever(error=PortError("down"))
    )

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "error"
    port_error_events = [e for e in tracer.events if e.name == "port_error"]
    assert len(port_error_events) == 1
    assert port_error_events[0].attributes["port"] == "retriever"


def test_answer_port_error_returns_error() -> None:
    chunks = [chunk("moves/hack-and-slash")]
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": [PortError("timeout")],
        }
    )
    assistant, _ = make_assistant(llm, retriever=FakeRetriever(chunks))

    result = asyncio.run(assistant.run(turn()))

    assert result.reply.kind == "error"
