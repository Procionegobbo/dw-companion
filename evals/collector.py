"""A tracer tap that buffers records per trace, so the runner can read a
completed case's generations and events back out after the turn (and the judge
call, if any) have finished (spec 009 D8d/D9).

`CollectingTracer` satisfies `ports.tracer.Tracer` and is teed alongside the
primary tracer (Langfuse, or a fake in tests) via `backend.adapters.tee_tracer.
TeeTracer`, so it sees exactly what the primary tracer sees, with no risk of
blocking or raising (it only appends to in-memory lists).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent


@dataclass(frozen=True, slots=True)
class TraceRecords:
    nodes: tuple[NodeTrace, ...]
    generations: tuple[GenerationTrace, ...]
    events: tuple[TraceEvent, ...]


class CollectingTracer:
    """Satisfies `ports.tracer.Tracer`; never raises.

    Buffers every record by `trace_id` until `take` returns and forgets that
    trace's records, so a long run does not grow memory unboundedly.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, list[NodeTrace]] = {}
        self._generations: dict[str, list[GenerationTrace]] = {}
        self._events: dict[str, list[TraceEvent]] = {}

    def record_node(self, trace: NodeTrace) -> None:
        self._nodes.setdefault(trace.trace_id, []).append(trace)

    def record_generation(self, trace: GenerationTrace) -> None:
        self._generations.setdefault(trace.trace_id, []).append(trace)

    def record_event(self, event: TraceEvent) -> None:
        self._events.setdefault(event.trace_id, []).append(event)

    def take(self, trace_id: str) -> TraceRecords:
        return TraceRecords(
            nodes=tuple(self._nodes.pop(trace_id, [])),
            generations=tuple(self._generations.pop(trace_id, [])),
            events=tuple(self._events.pop(trace_id, [])),
        )
