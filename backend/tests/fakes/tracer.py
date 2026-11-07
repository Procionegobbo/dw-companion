"""Hand-written fake for the `Tracer` port (spec 006 Testing)."""

from __future__ import annotations

from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent


class FakeTracer:
    def __init__(self) -> None:
        self.nodes: list[NodeTrace] = []
        self.generations: list[GenerationTrace] = []
        self.events: list[TraceEvent] = []

    def record_node(self, trace: NodeTrace) -> None:
        self.nodes.append(trace)

    def record_generation(self, trace: GenerationTrace) -> None:
        self.generations.append(trace)

    def record_event(self, event: TraceEvent) -> None:
        self.events.append(event)

    def event_names(self) -> list[str]:
        return [event.name for event in self.events]
