"""The `retrieve`, `answer_with_citations` and `citation_validator` nodes
(spec 006 Graph Behaviour: Rules branch).

Each node is a factory closing over `GraphDeps`, wrapped in `traced` so it stays a
plain async function testable through the compiled graph (D2).
`citation_validator` is deterministic and never calls a port: anti-hallucination
by code, not prompts (D12/D13).
"""

from __future__ import annotations

from collections.abc import Mapping

from backend.graph.citations import check_citations
from backend.graph.deps import GraphDeps
from backend.graph.prompts import RULES_SYSTEM, rules_user
from backend.graph.replies import NOT_FOUND_TEXT, error_reply
from backend.graph.state import Citation, GraphState, Reply
from backend.graph.tracing import NodeFn, call_llm, traced
from backend.ports.errors import PortError
from backend.ports.llm import LLMRequest
from backend.ports.retriever import RetrievedChunk
from backend.ports.tracer import TraceEvent


def make_retrieve(deps: GraphDeps) -> NodeFn:
    async def retrieve(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        try:
            chunks: tuple[RetrievedChunk, ...] = tuple(
                await deps.retriever.retrieve(turn.message, deps.settings.retrieval_k)
            )
        except PortError as exc:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="retrieve",
                    name="port_error",
                    attributes={"port": "retriever", "error": str(exc)},
                )
            )
            return {"reply": error_reply()}

        if not chunks:
            return {
                "chunks": chunks,
                "reply": Reply(kind="rules_not_found", text=NOT_FOUND_TEXT),
            }
        return {"chunks": chunks}

    return traced("retrieve", deps, retrieve)


def make_answer_with_citations(deps: GraphDeps) -> NodeFn:
    async def answer_with_citations(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        chunks = state.get("chunks", ())
        request = LLMRequest(
            role="answer",
            system=RULES_SYSTEM,
            user=rules_user(turn.message, chunks),
            max_tokens=deps.settings.answer_max_tokens,
            temperature=deps.settings.answer_temperature,
        )
        result = await call_llm(deps, state, "answer_with_citations", request)
        if isinstance(result, Reply):
            return {"reply": result}
        return {"draft_answer": result.text}

    return traced("answer_with_citations", deps, answer_with_citations)


def make_citation_validator(deps: GraphDeps) -> NodeFn:
    async def citation_validator(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        chunks = state.get("chunks", ())
        draft_answer = state.get("draft_answer", "")
        retrieved_ids = {chunk.section_id for chunk in chunks}
        check = check_citations(draft_answer, retrieved_ids)

        result: dict[str, object] = {
            "valid_citations": len(check.valid_ids),
            "stripped_citations": len(check.invalid_ids),
        }

        if check.invalid_ids:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="citation_validator",
                    name="citations_stripped",
                    attributes={
                        "ids": ",".join(check.invalid_ids),
                        "count": len(check.invalid_ids),
                    },
                )
            )

        if check.valid_ids:
            chunk_by_id = {chunk.section_id: chunk for chunk in chunks}
            citations = tuple(
                Citation(
                    section_id=chunk_id,
                    title=chunk_by_id[chunk_id].title,
                    url=chunk_by_id[chunk_id].anchor_url,
                )
                for chunk_id in check.valid_ids
            )
            result["reply"] = Reply(
                kind="rules_answer", text=check.text, citations=citations
            )
            return result

        deps.tracer.record_event(
            TraceEvent(
                trace_id=turn.trace_id,
                session_id=turn.session_id,
                node="citation_validator",
                name="no_valid_citation",
                attributes={"retrieved": len(chunks)},
            )
        )
        closest = chunks[: deps.settings.closest_sections_limit]
        citations = tuple(
            Citation(section_id=c.section_id, title=c.title, url=c.anchor_url)
            for c in closest
        )
        result["reply"] = Reply(
            kind="rules_not_found", text=NOT_FOUND_TEXT, citations=citations
        )
        return result

    return traced("citation_validator", deps, citation_validator)
