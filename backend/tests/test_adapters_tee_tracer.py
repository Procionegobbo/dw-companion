"""Tests for the `TeeTracer` adapter (spec 009 D8d)."""

from __future__ import annotations

import logging

import pytest

from backend.adapters.tee_tracer import TeeTracer
from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent
from backend.tests.fakes.tracer import FakeTracer

TRACE_A = "ab" * 16


def _node() -> NodeTrace:
    return NodeTrace(
        trace_id=TRACE_A,
        session_id="s1",
        node="retrieve",
        latency_ms=1.0,
        attributes={},
    )


class _RecordingTracer:
    """A `Tracer` that appends a tag to a shared log on every call, so test order
    across delegates can be asserted directly."""

    def __init__(self, tag: str, log: list[str]) -> None:
        self._tag = tag
        self._log = log

    def record_node(self, trace: NodeTrace) -> None:
        self._log.append(f"{self._tag}:node")

    def record_generation(self, trace: GenerationTrace) -> None:
        self._log.append(f"{self._tag}:generation")

    def record_event(self, event: TraceEvent) -> None:
        self._log.append(f"{self._tag}:event")


class _BoomTracer:
    def record_node(self, trace: NodeTrace) -> None:
        raise RuntimeError("boom")

    def record_generation(self, trace: GenerationTrace) -> None:
        raise RuntimeError("boom")

    def record_event(self, event: TraceEvent) -> None:
        raise RuntimeError("boom")


def test_tee_forwards_all_records_in_order() -> None:
    log: list[str] = []
    tee = TeeTracer(_RecordingTracer("a", log), _RecordingTracer("b", log))

    tee.record_node(_node())

    assert log == ["a:node", "b:node"]


def test_tee_swallows_and_logs_delegate_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    second = FakeTracer()
    tee = TeeTracer(_BoomTracer(), second)

    with caplog.at_level(logging.WARNING, logger="backend.adapters.tee_tracer"):
        tee.record_node(_node())

    assert second.nodes == [_node()]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == "tracer delegate failed: RuntimeError"


def test_tee_requires_two_delegates() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        TeeTracer(FakeTracer())
