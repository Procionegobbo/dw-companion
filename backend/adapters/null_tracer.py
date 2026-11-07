"""No-op tracer used when Langfuse is not configured (D18)."""

from __future__ import annotations

from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent


class NullTracer:
    """Satisfies `ports.tracer.Tracer`; every method is a no-op."""

    def record_node(self, trace: NodeTrace) -> None:
        return None

    def record_generation(self, trace: GenerationTrace) -> None:
        return None

    def record_event(self, event: TraceEvent) -> None:
        return None

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None
