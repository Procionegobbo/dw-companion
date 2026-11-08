"""Tests for the Langfuse tracer adapter and the null tracer (spec 007 Testing).

Exercises the real `langfuse` SDK against an injected OpenTelemetry
`InMemorySpanExporter` (`memory_tracer`, spec 007 D21), so the exported span
attributes are checked against the real wire shape rather than a hand-rolled fake.
Attribute keys come from `langfuse.LangfuseOtelSpanAttributes`; JSON-valued
attributes are decoded with `json.loads`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from uuid import uuid4

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from backend.adapters.langfuse_tracer import LangfuseTracer, make_langfuse_tracer
from backend.adapters.null_tracer import NullTracer
from backend.ports.llm import LLMRequest, LLMResponse
from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent, Tracer
from backend.tests.adapter_helpers import memory_exporter, memory_tracer

TRACE_A = "ab" * 16
TRACE_B = "cd" * 16


def _trace_id_hex(span: ReadableSpan) -> str:
    assert span.context is not None
    return format(span.context.trace_id, "032x")


def _duration_ms(span: ReadableSpan) -> float:
    assert span.start_time is not None
    assert span.end_time is not None
    return (span.end_time - span.start_time) / 1_000_000


def _attrs(span: ReadableSpan) -> Mapping[str, object]:
    assert span.attributes is not None
    return span.attributes


def _request(**overrides: object) -> LLMRequest:
    fields: dict[str, object] = {
        "role": "answer",
        "system": "You are the assistant.",
        "user": "How does Hack and Slash work?",
        "max_tokens": 700,
        "temperature": 0.0,
    }
    fields.update(overrides)
    return LLMRequest(**fields)  # type: ignore[arg-type]


def _response(**overrides: object) -> LLMResponse:
    fields: dict[str, object] = {
        "text": "Deal damage.",
        "model": "openai/x",
        "input_tokens": 12,
        "output_tokens": 7,
        "cost_usd": 0.00042,
    }
    fields.update(overrides)
    return LLMResponse(**fields)  # type: ignore[arg-type]


def _metadata(attrs: Mapping[str, object], key: str) -> object:
    raw = attrs[f"langfuse.observation.metadata.{key}"]
    assert isinstance(raw, str)
    return json.loads(raw)


def _trace_metadata(attrs: Mapping[str, object], key: str) -> object:
    raw = attrs[f"langfuse.trace.metadata.{key}"]
    assert isinstance(raw, str)
    return json.loads(raw)


def test_node_span_exported() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="retrieve",
            latency_ms=12.5,
            attributes={"count": 6},
        )
    )
    tracer.flush()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "retrieve"
    assert _trace_id_hex(span) == TRACE_A
    attrs = _attrs(span)
    assert attrs["session.id"] == "s1"
    assert attrs["langfuse.trace.name"] == "chat_turn"
    assert _metadata(attrs, "count") == 6
    assert _metadata(attrs, "latency_ms") == 12.5
    assert abs(_duration_ms(span) - 12.5) < 1.0


def test_non_hex_trace_id_mapped_deterministically() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_node(
        NodeTrace(
            trace_id="t1",
            session_id="s1",
            node="router",
            latency_ms=1.0,
            attributes={},
        )
    )
    tracer.flush()

    span = exporter.get_finished_spans()[0]
    assert _trace_id_hex(span) == Langfuse.create_trace_id(seed="t1")


def test_generation_has_model_usage_and_cost() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_generation(
        GenerationTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="answer",
            request=_request(),
            response=_response(
                model="openai/x", input_tokens=12, output_tokens=7, cost_usd=0.00042
            ),
            latency_ms=5.0,
        )
    )
    tracer.flush()

    span = exporter.get_finished_spans()[0]
    attrs = span.attributes
    assert attrs is not None
    assert attrs["langfuse.observation.type"] == "generation"
    assert attrs["langfuse.observation.model.name"] == "openai/x"
    assert json.loads(attrs["langfuse.observation.usage_details"]) == {  # type: ignore[arg-type]
        "input": 12,
        "output": 7,
    }
    assert json.loads(attrs["langfuse.observation.cost_details"]) == {  # type: ignore[arg-type]
        "total": 0.00042
    }
    model_parameters = json.loads(attrs["langfuse.observation.model.parameters"])  # type: ignore[arg-type]
    assert "max_tokens" in model_parameters


def test_generation_without_cost_has_no_cost_details() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_generation(
        GenerationTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="answer",
            request=_request(),
            response=_response(cost_usd=None),
            latency_ms=5.0,
        )
    )
    tracer.flush()

    attrs = exporter.get_finished_spans()[0].attributes
    assert attrs is not None
    assert "langfuse.observation.cost_details" not in attrs


def test_intent_propagates_after_router() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="router",
            latency_ms=1.0,
            attributes={"intent": "rules_question"},
        )
    )
    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="retrieve",
            latency_ms=1.0,
            attributes={"count": 1},
        )
    )
    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_B,
            session_id="s1",
            node="retrieve",
            latency_ms=1.0,
            attributes={"count": 1},
        )
    )
    tracer.flush()

    by_trace: dict[str, list[ReadableSpan]] = {}
    for span in exporter.get_finished_spans():
        by_trace.setdefault(_trace_id_hex(span), []).append(span)

    for span in by_trace[TRACE_A]:
        assert "intent:rules_question" in _attrs(span)["langfuse.trace.tags"]  # type: ignore[operator]

    for span in by_trace[TRACE_B]:
        assert "langfuse.trace.tags" not in _attrs(span)


def test_event_levels() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_event(
        TraceEvent(
            trace_id=TRACE_A,
            session_id="s1",
            node="answer_with_citations",
            name="port_error",
            attributes={},
        )
    )
    tracer.record_event(
        TraceEvent(
            trace_id=TRACE_A,
            session_id="s1",
            node="citation_validator",
            name="citations_stripped",
            attributes={},
        )
    )
    tracer.record_event(
        TraceEvent(
            trace_id=TRACE_A,
            session_id="s1",
            node="classify_move",
            name="clarification_requested",
            attributes={},
        )
    )
    tracer.flush()

    levels: dict[str, object] = {
        span.name: _attrs(span)["langfuse.observation.level"]
        for span in exporter.get_finished_spans()
    }
    assert levels["port_error"] == "ERROR"
    assert levels["citations_stripped"] == "WARNING"
    assert levels["clarification_requested"] == "DEFAULT"


def test_error_node_level() -> None:
    tracer, exporter = memory_tracer()

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="answer_with_citations",
            latency_ms=1.0,
            attributes={"error": True},
        )
    )
    tracer.flush()

    attrs = exporter.get_finished_spans()[0].attributes
    assert attrs is not None
    assert attrs["langfuse.observation.level"] == "ERROR"


def test_tracer_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    tracer, _ = memory_tracer()

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(Langfuse, "start_observation", _raise)
    monkeypatch.setattr(Langfuse, "create_event", _raise)

    with caplog.at_level(logging.WARNING, logger="backend.adapters.langfuse"):
        assert (
            tracer.record_node(
                NodeTrace(
                    trace_id=TRACE_A,
                    session_id="s1",
                    node="retrieve",
                    latency_ms=1.0,
                    attributes={},
                )
            )
            is None
        )
        assert (
            tracer.record_generation(
                GenerationTrace(
                    trace_id=TRACE_A,
                    session_id="s1",
                    node="answer",
                    request=_request(),
                    response=_response(),
                    latency_ms=1.0,
                )
            )
            is None
        )
        assert (
            tracer.record_event(
                TraceEvent(
                    trace_id=TRACE_A,
                    session_id="s1",
                    node="retrieve",
                    name="port_error",
                    attributes={},
                )
            )
            is None
        )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 3
    assert all("RuntimeError" in r.getMessage() for r in warnings)


def test_null_tracer_accepts_everything() -> None:
    tracer = NullTracer()

    assert (
        tracer.record_node(
            NodeTrace(
                trace_id=TRACE_A,
                session_id="s1",
                node="retrieve",
                latency_ms=1.0,
                attributes={},
            )
        )
        is None
    )
    assert (
        tracer.record_generation(
            GenerationTrace(
                trace_id=TRACE_A,
                session_id="s1",
                node="answer",
                request=_request(),
                response=_response(),
                latency_ms=1.0,
            )
        )
        is None
    )
    assert (
        tracer.record_event(
            TraceEvent(
                trace_id=TRACE_A,
                session_id="s1",
                node="retrieve",
                name="port_error",
                attributes={},
            )
        )
        is None
    )
    assert tracer.flush() is None
    assert tracer.close() is None


def _tracer_with_options(
    *,
    trace_name: str = "chat_turn",
    static_metadata: Mapping[str, str] | None = None,
    static_tags: tuple[str, ...] = (),
) -> tuple[LangfuseTracer, InMemorySpanExporter]:
    exporter = memory_exporter()
    tracer = make_langfuse_tracer(
        f"pk-test-{uuid4().hex}",
        "sk-test",
        "https://langfuse.invalid",
        span_exporter=exporter,
        trace_name=trace_name,
        static_metadata=static_metadata,
        static_tags=static_tags,
    )
    return tracer, exporter


def test_default_options_unchanged() -> None:
    tracer, exporter = _tracer_with_options()

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="retrieve",
            latency_ms=1.0,
            attributes={},
        )
    )
    tracer.flush()

    span = exporter.get_finished_spans()[0]
    attrs = _attrs(span)
    assert attrs["langfuse.trace.name"] == "chat_turn"
    assert not any(key.startswith("langfuse.trace.metadata.") for key in attrs)
    assert "langfuse.trace.tags" not in attrs


def test_static_metadata_and_tags_on_every_observation() -> None:
    tracer, exporter = _tracer_with_options(
        static_metadata={"eval_config": "baseline"},
        static_tags=("eval", "config:baseline"),
    )

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="router",
            latency_ms=1.0,
            attributes={"intent": "rules_question"},
        )
    )
    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="retrieve",
            latency_ms=1.0,
            attributes={"count": 1},
        )
    )
    tracer.flush()

    spans = {span.name: span for span in exporter.get_finished_spans()}

    router_attrs = _attrs(spans["router"])
    assert _trace_metadata(router_attrs, "eval_config") == "baseline"
    assert "eval" in router_attrs["langfuse.trace.tags"]  # type: ignore[operator]
    assert "config:baseline" in router_attrs["langfuse.trace.tags"]  # type: ignore[operator]

    retrieve_attrs = _attrs(spans["retrieve"])
    assert _trace_metadata(retrieve_attrs, "eval_config") == "baseline"
    assert _trace_metadata(retrieve_attrs, "intent") == "rules_question"
    tags = retrieve_attrs["langfuse.trace.tags"]
    assert "eval" in tags  # type: ignore[operator]
    assert "config:baseline" in tags  # type: ignore[operator]
    assert "intent:rules_question" in tags  # type: ignore[operator]


def test_custom_trace_name() -> None:
    tracer, exporter = _tracer_with_options(trace_name="eval_turn")

    tracer.record_node(
        NodeTrace(
            trace_id=TRACE_A,
            session_id="s1",
            node="retrieve",
            latency_ms=1.0,
            attributes={},
        )
    )
    tracer.flush()

    span = exporter.get_finished_spans()[0]
    assert _attrs(span)["langfuse.trace.name"] == "eval_turn"


def test_tracers_satisfy_protocol() -> None:
    langfuse_tracer, _ = memory_tracer()
    null_tracer = NullTracer()

    satisfies_langfuse: Tracer = langfuse_tracer
    satisfies_null: Tracer = null_tracer

    assert isinstance(satisfies_langfuse, LangfuseTracer)
    assert isinstance(satisfies_null, NullTracer)
