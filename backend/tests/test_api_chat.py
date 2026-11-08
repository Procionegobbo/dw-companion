"""Tests for `POST /api/chat`'s happy paths and post-stream failures, and
`GET /api/health` (spec 008 Testing)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.messages import TIMEOUT_TEXT
from backend.composition import ConfigError
from backend.graph.replies import ERROR_TEXT
from backend.graph.state import NodeCompleted, TurnInput
from backend.ports.errors import PortError
from backend.tests.api_helpers import SlowLLMClient, make_client, parse_sse, post_chat
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import chunk as fake_chunk
from backend.tests.graph_helpers import classifier_json, router_json

TRACE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
FIXED_TRACE = "ab" * 16


def test_health_ok() -> None:
    client, _state = make_client(FakeLLMClient({}))

    with client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_rules_question_streams_status_then_reply() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage. [[moves/hack-and-slash]]"],
        }
    )
    retriever = FakeRetriever(
        [fake_chunk("moves/hack-and-slash", title="Hack and Slash")]
    )
    client, _state = make_client(llm, retriever=retriever)

    with client:
        response = post_chat(client, {"message": "How does hack and slash work?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"

    events = parse_sse(response.text)
    assert [name for name, _ in events] == [
        "status",
        "status",
        "status",
        "status",
        "reply",
    ]
    steps = [data["step"] for name, data in events if name == "status"]
    assert steps == [
        "router",
        "retrieve",
        "answer_with_citations",
        "citation_validator",
    ]

    reply = events[-1][1]
    assert reply["kind"] == "rules_answer"
    assert reply["citations"][0]["url"] == "/rules/moves/hack-and-slash/"
    assert TRACE_PATTERN.match(reply["trace_id"])


def test_move_turn_with_roll_and_modifier() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash", 0.9, stat="STR")],
            "answer": ["You swing your sword, triggering Hack and Slash."],
        }
    )
    client, _state = make_client(llm, rng=ScriptedRandom([4, 5]))

    with client:
        response = post_chat(
            client,
            {
                "message": "I swing my sword at the goblin",
                "roll": True,
                "modifier": 1,
            },
        )

    events = parse_sse(response.text)
    reply = events[-1][1]
    assert reply["move"]["roll"] == {"dice": [4, 5], "modifier": 1, "total": 10}
    assert reply["move"]["outcome"]["band"] == "strong_hit"


def test_out_of_scope_turn() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": "what's the weather like"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "status", "reply"]
    steps = [data["step"] for name, data in events if name == "status"]
    assert steps == ["router", "out_of_scope"]
    assert events[-1][1]["kind"] == "out_of_scope"


def test_graph_error_is_reply_event() -> None:
    llm = FakeLLMClient({"router": [PortError("down")]})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": "hi"})

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[-1] == "reply"
    assert "error" not in names
    reply = events[-1][1]
    assert reply["kind"] == "error"
    assert reply["text"] == ERROR_TEXT


def test_unexpected_exception_emits_error_event(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _BoomAssistant:
        async def stream(self, turn: TurnInput) -> Any:
            yield NodeCompleted("router")
            raise RuntimeError("boom")

    class _BoomRuntime:
        def __init__(self) -> None:
            self.assistant = _BoomAssistant()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("backend.api.app.uuid4", lambda: uuid.UUID(hex=FIXED_TRACE))

    app = create_app(
        environ={},
        runtime_factory=lambda _sink: _BoomRuntime(),  # pyright: ignore[reportArgumentType]
    )
    client = TestClient(app)

    with caplog.at_level(logging.ERROR, logger="backend.api"), client:
        response = post_chat(
            client, {"message": "some secret message", "session_id": "cd" * 16}
        )

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "error"]
    assert events[-1][1] == {"code": "internal_error", "message": ERROR_TEXT}

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in log_text
    assert FIXED_TRACE in log_text
    assert "some secret message" not in log_text


def test_turn_timeout_emits_error_event() -> None:
    client, _state = make_client(SlowLLMClient(1.0), turn_timeout_s=0.05)

    with client:
        response = post_chat(client, {"message": "hi"})

    events = parse_sse(response.text)
    assert events[-1] == ("error", {"code": "timeout", "message": TIMEOUT_TEXT})


def test_session_id_passed_through() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, state = make_client(llm)
    session_id = "ab" * 16

    with client:
        post_chat(client, {"message": "hi", "session_id": session_id})

    assert state.tracer.nodes
    assert all(node.session_id == session_id for node in state.tracer.nodes)


def test_session_id_generated_when_absent() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, state = make_client(llm)

    with client:
        post_chat(client, {"message": "hi"})

    session_ids = {node.session_id for node in state.tracer.nodes}
    assert len(session_ids) == 1
    assert TRACE_PATTERN.match(next(iter(session_ids)))


def test_trace_id_fresh_per_request() -> None:
    llm = FakeLLMClient(
        {"router": [router_json("out_of_scope"), router_json("out_of_scope")]}
    )
    client, state = make_client(llm)

    with client:
        response_a = post_chat(client, {"message": "hi"})
        response_b = post_chat(client, {"message": "hi"})

    trace_a = parse_sse(response_a.text)[-1][1]["trace_id"]
    trace_b = parse_sse(response_b.text)[-1][1]["trace_id"]
    assert trace_a != trace_b

    trace_ids = {node.trace_id for node in state.tracer.nodes}
    assert trace_ids == {trace_a, trace_b}


def test_message_stripped_before_graph() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, _state = make_client(llm)

    with client:
        post_chat(client, {"message": "  hi  "})

    assert len(llm.requests) == 1
    assert "<user_message>\nhi\n</user_message>" in llm.requests[0].user


def test_every_llm_request_has_max_tokens() -> None:
    rules_llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage. [[moves/hack-and-slash]]"],
        }
    )
    rules_client, _rules_state = make_client(
        rules_llm, retriever=FakeRetriever([fake_chunk("moves/hack-and-slash")])
    )
    with rules_client:
        post_chat(rules_client, {"message": "How does hack and slash work?"})
    assert [r.max_tokens for r in rules_llm.requests] == [100, 700]

    move_llm = FakeLLMClient(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("hack-and-slash", 0.9, stat="STR")],
            "answer": ["You swing your sword, triggering Hack and Slash."],
        }
    )
    move_client, _move_state = make_client(move_llm, rng=ScriptedRandom([4, 5]))
    with move_client:
        post_chat(
            move_client,
            {
                "message": "I swing my sword at the goblin",
                "roll": True,
                "modifier": 1,
            },
        )
    assert [r.max_tokens for r in move_llm.requests] == [100, 400, 300]


def test_runtime_closed_on_shutdown() -> None:
    llm = FakeLLMClient({})
    client, state = make_client(llm)

    assert state.closed is False
    with client:
        pass
    assert state.closed is True


def test_create_app_rejects_invalid_settings() -> None:
    with pytest.raises(ConfigError):
        create_app(environ={"CHAT_RATE_PER_MINUTE": "0"})


def test_default_factory_fails_fast_without_config() -> None:
    app = create_app(environ={})

    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"), TestClient(app):
        pass
