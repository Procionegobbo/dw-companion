"""Node tracing wrapper and the `call_llm` helper (spec 006 Tracing, D20).

`traced` wraps every node: it measures `deps.clock()` before and after the node
runs, then records one `NodeTrace` (recorded even when the node produced an error
reply, whose attributes are exactly `{"error": True}`). `call_llm` wraps every LLM
call: it records a `GenerationTrace`, or on `PortError` records a `port_error`
event and returns the fixed error `Reply` instead of raising.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from backend.domain.dice import Roll
from backend.graph.deps import GraphDeps
from backend.graph.llm_outputs import MoveClassification
from backend.graph.replies import error_reply
from backend.graph.state import GraphState, Reply
from backend.ports.errors import PortError
from backend.ports.llm import LLMRequest, LLMResponse
from backend.ports.tracer import AttributeValue, GenerationTrace, NodeTrace, TraceEvent

NodeFn = Callable[[GraphState], Awaitable[Mapping[str, object]]]


def _attributes_for(
    name: str, result: Mapping[str, object]
) -> Mapping[str, AttributeValue]:
    reply = result.get("reply")
    if isinstance(reply, Reply) and reply.kind == "error":
        return {"error": True}
    if name == "router":
        return {
            "intent": cast(AttributeValue, result.get("intent")),
            "confidence": cast(AttributeValue, result.get("router_confidence")),
        }
    if name == "retrieve":
        chunks = cast("tuple[object, ...]", result.get("chunks", ()))
        return {"count": len(chunks)}
    if name == "citation_validator":
        return {
            "valid": cast(AttributeValue, result.get("valid_citations")),
            "stripped": cast(AttributeValue, result.get("stripped_citations")),
        }
    if name == "classify_move":
        classification = cast("MoveClassification | None", result.get("classification"))
        return {
            "move_id": classification.move_id if classification is not None else None,
            "confidence": (
                classification.confidence if classification is not None else None
            ),
            "roll_stat": cast(AttributeValue, result.get("roll_stat")),
        }
    if name == "roll":
        rolled = cast("Roll | None", result.get("roll"))
        return {"dice_total": rolled.dice_total if rolled is not None else None}
    return {}


def traced(name: str, deps: GraphDeps, node_fn: NodeFn) -> NodeFn:
    async def wrapped(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        start = deps.clock()
        result = await node_fn(state)
        end = deps.clock()
        deps.tracer.record_node(
            NodeTrace(
                trace_id=turn.trace_id,
                session_id=turn.session_id,
                node=name,
                latency_ms=(end - start) * 1000,
                attributes=_attributes_for(name, result),
            )
        )
        return result

    return wrapped


async def call_llm(
    deps: GraphDeps, state: GraphState, node: str, request: LLMRequest
) -> LLMResponse | Reply:
    turn = state["turn"]
    start = deps.clock()
    try:
        response = await deps.llm.generate(request)
    except PortError as exc:
        deps.tracer.record_event(
            TraceEvent(
                trace_id=turn.trace_id,
                session_id=turn.session_id,
                node=node,
                name="port_error",
                attributes={"port": "llm", "error": str(exc)},
            )
        )
        return error_reply()
    end = deps.clock()
    deps.tracer.record_generation(
        GenerationTrace(
            trace_id=turn.trace_id,
            session_id=turn.session_id,
            node=node,
            request=request,
            response=response,
            latency_ms=(end - start) * 1000,
        )
    )
    return response
