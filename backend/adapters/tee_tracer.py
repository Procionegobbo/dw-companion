"""Tees every tracer record to two or more delegates (D8d).

Used by `build_runtime`'s `tracer_tap` wiring so an eval run can both export to
Langfuse and collect records locally without changing the primary tracer.
"""

from __future__ import annotations

import logging

from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent, Tracer

logger = logging.getLogger("backend.adapters.tee_tracer")


class TeeTracer:
    """Satisfies `ports.tracer.Tracer` by forwarding every record to each
    delegate, in order.

    A delegate that raises is logged at WARNING and otherwise ignored, so the
    tee still satisfies the port's never-raise contract even when one delegate
    misbehaves.
    """

    def __init__(self, *tracers: Tracer) -> None:
        if len(tracers) < 2:
            raise ValueError("invalid TeeTracer: at least 2 tracers are required")
        self._tracers = tracers

    def record_node(self, trace: NodeTrace) -> None:
        for tracer in self._tracers:
            try:
                tracer.record_node(trace)
            except Exception as exc:
                logger.warning("tracer delegate failed: %s", type(exc).__name__)

    def record_generation(self, trace: GenerationTrace) -> None:
        for tracer in self._tracers:
            try:
                tracer.record_generation(trace)
            except Exception as exc:
                logger.warning("tracer delegate failed: %s", type(exc).__name__)

    def record_event(self, event: TraceEvent) -> None:
        for tracer in self._tracers:
            try:
                tracer.record_event(event)
            except Exception as exc:
                logger.warning("tracer delegate failed: %s", type(exc).__name__)
