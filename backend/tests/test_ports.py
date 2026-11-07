"""Tests for the port protocols and their value types (spec 006 Testing).

Covers `LLMRequest`/`LLMResponse` (`backend/ports/llm.py`), `RetrievedChunk`
(`backend/ports/retriever.py`), the trace records (`backend/ports/tracer.py`), and the
four fakes under `backend/tests/fakes/`.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from typing import cast

import pytest

from backend.ports.llm import LLMClient, LLMRequest, LLMResponse
from backend.ports.retriever import ChunkType, RetrievedChunk, Retriever
from backend.ports.rulebook import RulebookRepository
from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent, Tracer
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.rulebook import FakeRulebookRepository
from backend.tests.fakes.tracer import FakeTracer


def _make_request(
    *,
    system: str = "system prompt",
    user: str = "user prompt",
    max_tokens: int = 100,
    temperature: float = 0.0,
    response_schema: dict[str, object] | None = None,
    schema_name: str | None = None,
) -> LLMRequest:
    return LLMRequest(
        role="router",
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        response_schema=response_schema,
        schema_name=schema_name,
    )


@pytest.mark.parametrize(
    ("name", "match", "factory"),
    [
        ("empty system", "system", lambda: _make_request(system="   ")),
        ("max_tokens zero", "max_tokens", lambda: _make_request(max_tokens=0)),
        (
            "temperature negative",
            "temperature",
            lambda: _make_request(temperature=-0.1),
        ),
        (
            "temperature nan",
            "temperature",
            lambda: _make_request(temperature=math.nan),
        ),
        (
            "schema_name without schema",
            "schema_name",
            lambda: _make_request(schema_name="router_decision"),
        ),
        (
            "schema without schema_name",
            "schema_name",
            lambda: _make_request(response_schema={"type": "object"}),
        ),
        (
            "bad schema_name",
            "schema_name",
            lambda: _make_request(
                response_schema={"type": "object"}, schema_name="Bad Name"
            ),
        ),
    ],
)
def test_llm_request_validation(
    name: str, match: str, factory: Callable[[], LLMRequest]
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_llm_request_valid_constructs() -> None:
    request = _make_request()
    assert request.role == "router"
    assert request.response_schema is None
    assert request.schema_name is None


def test_llm_response_validation() -> None:
    with pytest.raises(ValueError, match="input_tokens"):
        LLMResponse(text="x", model="m", input_tokens=-1, output_tokens=5)
    with pytest.raises(ValueError, match="output_tokens"):
        LLMResponse(text="x", model="m", input_tokens=5, output_tokens=-1)
    with pytest.raises(ValueError, match="model"):
        LLMResponse(text="x", model="   ", input_tokens=5, output_tokens=5)

    response = LLMResponse(text="", model="m", input_tokens=5, output_tokens=5)
    assert response.text == ""


def test_retrieved_chunk_validation() -> None:
    with pytest.raises(ValueError, match="section_id"):
        RetrievedChunk(
            section_id="   ",
            title="Title",
            chapter="moves",
            anchor_url="/rules/moves/x/",
            type="section",
            text="t",
            score=0.9,
        )
    with pytest.raises(ValueError, match="anchor_url"):
        RetrievedChunk(
            section_id="moves/x",
            title="Title",
            chapter="moves",
            anchor_url="rules/x",
            type="section",
            text="t",
            score=0.9,
        )
    with pytest.raises(ValueError, match="type"):
        RetrievedChunk(
            section_id="moves/x",
            title="Title",
            chapter="moves",
            anchor_url="/rules/moves/x/",
            type=cast(ChunkType, "page"),
            text="t",
            score=0.9,
        )
    with pytest.raises(ValueError, match="score"):
        RetrievedChunk(
            section_id="moves/x",
            title="Title",
            chapter="moves",
            anchor_url="/rules/moves/x/",
            type="section",
            text="t",
            score=math.inf,
        )


def test_trace_records_validation() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        NodeTrace(
            trace_id="t1",
            session_id="s1",
            node="router",
            latency_ms=-1.0,
            attributes={},
        )
    with pytest.raises(ValueError, match="node"):
        NodeTrace(
            trace_id="t1", session_id="s1", node="   ", latency_ms=1.0, attributes={}
        )

    request = _make_request()
    response = LLMResponse(text="x", model="m", input_tokens=1, output_tokens=1)
    with pytest.raises(ValueError, match="latency_ms"):
        GenerationTrace(
            trace_id="t1",
            session_id="s1",
            node="router",
            request=request,
            response=response,
            latency_ms=-1.0,
        )
    with pytest.raises(ValueError, match="node"):
        GenerationTrace(
            trace_id="t1",
            session_id="s1",
            node="   ",
            request=request,
            response=response,
            latency_ms=1.0,
        )

    with pytest.raises(ValueError, match="node"):
        TraceEvent(trace_id="t1", session_id="s1", node="   ", name="x", attributes={})
    with pytest.raises(ValueError, match="name"):
        TraceEvent(
            trace_id="t1", session_id="s1", node="router", name="   ", attributes={}
        )


def test_fakes_satisfy_protocols() -> None:
    llm: LLMClient = FakeLLMClient({})
    retriever: Retriever = FakeRetriever()
    tracer: Tracer = FakeTracer()
    rulebook: RulebookRepository = FakeRulebookRepository([])

    assert llm is not None
    assert retriever is not None
    assert tracer is not None
    assert rulebook is not None


def test_fake_llm_fails_on_unexpected_call() -> None:
    client = FakeLLMClient({})
    request = _make_request()
    with pytest.raises(AssertionError, match="unexpected router call"):
        asyncio.run(client.generate(request))


def test_fake_retriever_truncates_to_k() -> None:
    chunks = tuple(
        RetrievedChunk(
            section_id=f"moves/move-{i}",
            title=f"Move {i}",
            chapter="moves",
            anchor_url=f"/rules/moves/move-{i}/",
            type="section",
            text="t",
            score=1.0,
        )
        for i in range(8)
    )
    retriever = FakeRetriever(chunks)

    result = asyncio.run(retriever.retrieve("q", 6))

    assert len(result) == 6
    assert retriever.calls == [("q", 6)]
