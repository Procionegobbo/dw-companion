"""Langfuse tracer adapter: exports node, generation and event records (D14-D18).

Every `record_*` call runs inside `try/except Exception`: on failure it logs a WARNING
on logger `backend.adapters.langfuse` and returns `None`, never raising and never
blocking the graph (spec 006 D20). The official `langfuse` SDK batches and exports on
a background thread, which is how the never-block contract is met.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Final, Literal

from langfuse import Langfuse, propagate_attributes
from opentelemetry.sdk.trace.export import SpanExporter

from backend.ports.tracer import GenerationTrace, NodeTrace, TraceEvent

logger = logging.getLogger("backend.adapters.langfuse")

_MAX_REMEMBERED_INTENTS: Final = 1024

_TRACE_ID_HEX: Final = re.compile(r"^[0-9a-f]{32}$")

EventLevel = Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"]

_ERROR_EVENTS: Final = frozenset({"port_error", "llm_output_invalid"})
_WARNING_EVENTS: Final = frozenset(
    {
        "citations_stripped",
        "no_valid_citation",
        "classifier_unknown_move",
        "classifier_alternatives_stripped",
        "classifier_stat_overridden",
    }
)


def _event_level(name: str) -> EventLevel:
    if name in _ERROR_EVENTS:
        return "ERROR"
    if name in _WARNING_EVENTS:
        return "WARNING"
    return "DEFAULT"


def _trace_id_for(trace_id: str) -> str:
    if _TRACE_ID_HEX.fullmatch(trace_id):
        return trace_id
    return Langfuse.create_trace_id(seed=trace_id)


class LangfuseTracer:
    """Satisfies `ports.tracer.Tracer` by exporting observations to Langfuse.

    `trace_name`, `static_metadata` and `static_tags` (D7/D8c) default to spec
    007's exact behaviour: trace name `"chat_turn"`, no extra metadata or tags.
    Every observation carries the static metadata/tags; once the router has run
    for a trace, `"intent"`/`"intent:<x>"` are merged in on top of them.
    """

    def __init__(
        self,
        client: Langfuse,
        *,
        trace_name: str = "chat_turn",
        static_metadata: Mapping[str, str] | None = None,
        static_tags: Sequence[str] = (),
    ) -> None:
        self._client = client
        self._trace_name = trace_name
        self._static_metadata = dict(static_metadata) if static_metadata else {}
        self._static_tags = tuple(static_tags)
        self._intents: OrderedDict[str, str] = OrderedDict()

    def _remember_intent(self, trace_id: str, intent: str) -> None:
        self._intents[trace_id] = intent
        self._intents.move_to_end(trace_id)
        while len(self._intents) > _MAX_REMEMBERED_INTENTS:
            self._intents.popitem(last=False)

    def _propagate(
        self, trace_id: str, session_id: str
    ) -> AbstractContextManager[object]:
        intent = self._intents.get(trace_id)
        metadata: dict[str, str] = dict(self._static_metadata)
        tags: list[str] = list(self._static_tags)
        if intent is not None:
            metadata["intent"] = intent
            tags.append(f"intent:{intent}")

        if metadata and tags:
            return propagate_attributes(
                session_id=session_id,
                trace_name=self._trace_name,
                metadata=metadata,
                tags=tags,
            )
        if metadata:
            return propagate_attributes(
                session_id=session_id, trace_name=self._trace_name, metadata=metadata
            )
        if tags:
            return propagate_attributes(
                session_id=session_id, trace_name=self._trace_name, tags=tags
            )
        return propagate_attributes(session_id=session_id, trace_name=self._trace_name)

    def record_node(self, trace: NodeTrace) -> None:
        try:
            if trace.node == "router":
                intent = trace.attributes.get("intent")
                if isinstance(intent, str):
                    self._remember_intent(trace.trace_id, intent)

            langfuse_trace_id = _trace_id_for(trace.trace_id)
            metadata: dict[str, object] = {
                **trace.attributes,
                "latency_ms": trace.latency_ms,
            }
            level: EventLevel | None = (
                "ERROR" if trace.attributes.get("error") is True else None
            )

            with self._propagate(trace.trace_id, trace.session_id):
                t0 = time.time_ns()
                observation = self._client.start_observation(
                    trace_context={"trace_id": langfuse_trace_id},
                    as_type="span",
                    name=trace.node,
                    metadata=metadata,
                    level=level,
                )
                observation.end(end_time=t0 + int(trace.latency_ms * 1_000_000))
        except Exception as exc:
            logger.warning("langfuse record_node failed: %s", type(exc).__name__)
        return None

    def record_generation(self, trace: GenerationTrace) -> None:
        try:
            request = trace.request
            response = trace.response
            langfuse_trace_id = _trace_id_for(trace.trace_id)
            cost_details = (
                {"total": response.cost_usd} if response.cost_usd is not None else None
            )
            metadata: dict[str, object] = {
                "role": request.role,
                "schema_name": request.schema_name,
                "latency_ms": trace.latency_ms,
            }

            with self._propagate(trace.trace_id, trace.session_id):
                t0 = time.time_ns()
                observation = self._client.start_observation(
                    trace_context={"trace_id": langfuse_trace_id},
                    as_type="generation",
                    name=trace.node,
                    model=response.model,
                    model_parameters={
                        "max_tokens": request.max_tokens,
                        "temperature": request.temperature,
                    },
                    input=[
                        {"role": "system", "content": request.system},
                        {"role": "user", "content": request.user},
                    ],
                    output=response.text,
                    usage_details={
                        "input": response.input_tokens,
                        "output": response.output_tokens,
                    },
                    cost_details=cost_details,
                    metadata=metadata,
                )
                observation.end(end_time=t0 + int(trace.latency_ms * 1_000_000))
        except Exception as exc:
            logger.warning("langfuse record_generation failed: %s", type(exc).__name__)
        return None

    def record_event(self, event: TraceEvent) -> None:
        try:
            langfuse_trace_id = _trace_id_for(event.trace_id)
            with self._propagate(event.trace_id, event.session_id):
                self._client.create_event(
                    trace_context={"trace_id": langfuse_trace_id},
                    name=event.name,
                    metadata=dict(event.attributes),
                    level=_event_level(event.name),
                )
        except Exception as exc:
            logger.warning("langfuse record_event failed: %s", type(exc).__name__)
        return None

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:
            logger.warning("langfuse flush failed: %s", type(exc).__name__)

    def close(self) -> None:
        try:
            self._client.shutdown()
        except Exception as exc:
            logger.warning("langfuse close failed: %s", type(exc).__name__)


def make_langfuse_tracer(
    public_key: str,
    secret_key: str,
    base_url: str,
    *,
    span_exporter: SpanExporter | None = None,
    trace_name: str = "chat_turn",
    static_metadata: Mapping[str, str] | None = None,
    static_tags: Sequence[str] = (),
) -> LangfuseTracer:
    client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        span_exporter=span_exporter,
    )
    return LangfuseTracer(
        client,
        trace_name=trace_name,
        static_metadata=static_metadata,
        static_tags=static_tags,
    )
