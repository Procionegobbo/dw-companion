"""The `Tracer` port: node, generation and event records (D20).

Sync (D3): adapters must buffer and never block on network; the contract is that
`record_*` never raises.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from backend.ports.llm import LLMRequest, LLMResponse

AttributeValue = str | int | float | bool | None


def _require_non_empty(value: str, *, type_name: str, field: str) -> None:
    if not value.strip():
        raise ValueError(f"invalid {type_name}: {field} must be non-empty")


def _require_latency(value: float, *, type_name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid {type_name}: latency_ms must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class NodeTrace:
    trace_id: str
    session_id: str
    node: str
    latency_ms: float
    attributes: Mapping[str, AttributeValue]

    def __post_init__(self) -> None:
        _require_non_empty(self.trace_id, type_name="NodeTrace", field="trace_id")
        _require_non_empty(self.session_id, type_name="NodeTrace", field="session_id")
        _require_non_empty(self.node, type_name="NodeTrace", field="node")
        _require_latency(self.latency_ms, type_name="NodeTrace")


@dataclass(frozen=True, slots=True)
class GenerationTrace:
    trace_id: str
    session_id: str
    node: str
    request: LLMRequest
    response: LLMResponse
    latency_ms: float

    def __post_init__(self) -> None:
        _require_non_empty(self.trace_id, type_name="GenerationTrace", field="trace_id")
        _require_non_empty(
            self.session_id, type_name="GenerationTrace", field="session_id"
        )
        _require_non_empty(self.node, type_name="GenerationTrace", field="node")
        _require_latency(self.latency_ms, type_name="GenerationTrace")


@dataclass(frozen=True, slots=True)
class TraceEvent:
    trace_id: str
    session_id: str
    node: str
    name: str
    attributes: Mapping[str, AttributeValue]

    def __post_init__(self) -> None:
        _require_non_empty(self.trace_id, type_name="TraceEvent", field="trace_id")
        _require_non_empty(self.session_id, type_name="TraceEvent", field="session_id")
        _require_non_empty(self.node, type_name="TraceEvent", field="node")
        _require_non_empty(self.name, type_name="TraceEvent", field="name")


class Tracer(Protocol):
    # contract: never raises, never blocks on network
    def record_node(self, trace: NodeTrace) -> None: ...
    def record_generation(self, trace: GenerationTrace) -> None: ...
    def record_event(self, event: TraceEvent) -> None: ...
