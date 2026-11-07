"""The `router` and `out_of_scope` nodes (spec 006 Graph Behaviour: Router).

Each node is a factory closing over `GraphDeps`, wrapped in `traced` so it stays a
plain async function testable through the compiled graph (D2).
"""

from __future__ import annotations

from collections.abc import Mapping

from backend.graph.deps import GraphDeps
from backend.graph.llm_outputs import parse_router_output, router_schema
from backend.graph.prompts import ROUTER_SYSTEM, router_user
from backend.graph.replies import OUT_OF_SCOPE_TEXT, error_reply
from backend.graph.state import GraphState, Reply
from backend.graph.tracing import NodeFn, call_llm, traced
from backend.ports.llm import LLMRequest
from backend.ports.tracer import TraceEvent


def make_router(deps: GraphDeps) -> NodeFn:
    async def router(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        request = LLMRequest(
            role="router",
            system=ROUTER_SYSTEM,
            user=router_user(turn.message),
            max_tokens=deps.settings.router_max_tokens,
            temperature=0.0,
            response_schema=router_schema(),
            schema_name="router_decision",
        )
        result = await call_llm(deps, state, "router", request)
        if isinstance(result, Reply):
            return {"reply": result}

        try:
            decision = parse_router_output(result.text)
        except ValueError as exc:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="router",
                    name="llm_output_invalid",
                    attributes={"error": str(exc)},
                )
            )
            return {"reply": error_reply()}

        return {"intent": decision.intent, "router_confidence": decision.confidence}

    return traced("router", deps, router)


def make_out_of_scope(deps: GraphDeps) -> NodeFn:
    async def out_of_scope(state: GraphState) -> Mapping[str, object]:
        return {"reply": Reply(kind="out_of_scope", text=OUT_OF_SCOPE_TEXT)}

    return traced("out_of_scope", deps, out_of_scope)
