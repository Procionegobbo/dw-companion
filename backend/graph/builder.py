"""LangGraph wiring: the only module that imports `langgraph.*` (D2).

Nodes are plain `async` functions over `GraphState`; this module is the sole place
that touches LangGraph's API, so a major-version upgrade or a typing quirk (open
risk (a)) is contained here. Callers use `Assistant`, never a LangGraph type.
`compiled` is typed opaquely (`object`) on `Assistant` itself; internally `Assistant`
talks to it only through the small `_Compiled` protocol below, so the rest of the
module stays free of LangGraph's own (partially unknown, per open risk (a)) types.

Wiring: `START -> router`; `out_of_scope -> END`; `rules_question -> retrieve ->
answer_with_citations -> citation_validator -> END`; `action_description ->
classify_move`, which branches to `clarify -> END`, `no_move -> END`, or
`explain`, which branches to `roll -> outcome -> END` iff the turn asked for a
roll and the matched move is rolled, else `END`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Final, Protocol, cast

from langgraph.graph import END, START, StateGraph  # pyright: ignore[reportMissingTypeStubs]

from backend.graph.deps import GraphDeps
from backend.graph.llm_outputs import NO_MOVE
from backend.graph.move_branch import (
    make_clarify,
    make_classify_move,
    make_explain,
    make_no_move,
    make_outcome,
    make_roll,
)
from backend.graph.router import make_out_of_scope, make_router
from backend.graph.rules_branch import (
    make_answer_with_citations,
    make_citation_validator,
    make_retrieve,
)
from backend.graph.state import (
    AssistantEvent,
    GraphState,
    NodeCompleted,
    TurnInput,
    TurnResult,
)

_NODE_NAMES: Final = frozenset(
    {
        "router",
        "out_of_scope",
        "retrieve",
        "answer_with_citations",
        "citation_validator",
        "classify_move",
        "clarify",
        "no_move",
        "explain",
        "roll",
        "outcome",
    }
)


class _Compiled(Protocol):
    """The slice of a compiled LangGraph's API `Assistant` relies on."""

    async def ainvoke(self, state: Mapping[str, object], /) -> object: ...
    def astream(
        self, state: Mapping[str, object], /, *, stream_mode: Sequence[str]
    ) -> AsyncIterator[tuple[str, object]]: ...


def _route_after_router(state: GraphState) -> str:
    if "reply" in state:
        return END
    intent = state.get("intent")
    if intent == "out_of_scope":
        return "out_of_scope"
    if intent == "rules_question":
        return "retrieve"
    return "classify_move"


def _route_after_retrieve(state: GraphState) -> str:
    if "reply" in state:
        return END
    return "answer_with_citations"


def _route_after_answer(state: GraphState) -> str:
    if "reply" in state:
        return END
    return "citation_validator"


def _make_route_after_classify(deps: GraphDeps) -> Callable[[GraphState], str]:
    def _route_after_classify(state: GraphState) -> str:
        if "reply" in state:
            return END
        classification = state.get("classification")
        if classification is None:
            return END
        if classification.confidence < deps.settings.clarify_threshold:
            return "clarify"
        if classification.move_id == NO_MOVE:
            return "no_move"
        return "explain"

    return _route_after_classify


def _route_after_explain(state: GraphState) -> str:
    reply = state.get("reply")
    if reply is not None and reply.kind == "error":
        return END
    turn = state["turn"]
    move = state.get("move")
    if turn.roll_requested and move is not None and move.is_rolled:
        return "roll"
    return END


def _turn_result_from_state(state: GraphState) -> TurnResult:
    reply = state.get("reply")
    if reply is None:
        raise RuntimeError("graph finished without a reply")

    chunks = state.get("chunks", ())
    return TurnResult(
        reply=reply,
        intent=state.get("intent"),
        router_confidence=state.get("router_confidence"),
        classification=state.get("classification"),
        retrieved_section_ids=tuple(chunk.section_id for chunk in chunks),
    )


class Assistant:
    def __init__(self, compiled: object) -> None:
        self._compiled = compiled

    async def run(self, turn: TurnInput) -> TurnResult:
        compiled = cast(_Compiled, self._compiled)
        raw_state = await compiled.ainvoke({"turn": turn})
        state = cast(GraphState, raw_state) if raw_state else cast(GraphState, {})
        return _turn_result_from_state(state)

    async def stream(self, turn: TurnInput) -> AsyncIterator[AssistantEvent]:
        """Node-level progress then exactly one `TurnResult` (spec 008 D4).

        Confined to this module: it drives LangGraph's `astream` directly, the
        only place in the codebase that does (open risk (c)).
        """
        compiled = cast(_Compiled, self._compiled)
        latest_state: GraphState = cast(GraphState, {})
        async for mode, chunk in compiled.astream(
            {"turn": turn}, stream_mode=["updates", "values"]
        ):
            if mode == "updates":
                update = cast(Mapping[str, object], chunk)
                for name in update:
                    if name in _NODE_NAMES:
                        yield NodeCompleted(name)
            elif mode == "values":
                latest_state = cast(GraphState, chunk)
        yield _turn_result_from_state(latest_state)

    @property
    def compiled(self) -> object:
        return self._compiled


def _assistant_from_compiled(compiled: object) -> Assistant:
    return Assistant(compiled)


def build_assistant(deps: GraphDeps) -> Assistant:
    graph = StateGraph(GraphState)
    graph.add_node("router", make_router(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("out_of_scope", make_out_of_scope(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("retrieve", make_retrieve(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("answer_with_citations", make_answer_with_citations(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("citation_validator", make_citation_validator(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("classify_move", make_classify_move(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("clarify", make_clarify(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("no_move", make_no_move(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("explain", make_explain(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("roll", make_roll(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    graph.add_node("outcome", make_outcome(deps))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", _route_after_router)
    graph.add_edge("out_of_scope", END)
    graph.add_conditional_edges("retrieve", _route_after_retrieve)
    graph.add_conditional_edges("answer_with_citations", _route_after_answer)
    graph.add_edge("citation_validator", END)
    graph.add_conditional_edges("classify_move", _make_route_after_classify(deps))
    graph.add_edge("clarify", END)
    graph.add_edge("no_move", END)
    graph.add_conditional_edges("explain", _route_after_explain)
    graph.add_edge("roll", "outcome")
    graph.add_edge("outcome", END)

    compiled = graph.compile()  # pyright: ignore[reportUnknownMemberType]
    return _assistant_from_compiled(compiled)
