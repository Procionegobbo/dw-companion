"""The `classify_move`, `clarify`, `no_move`, `explain`, `roll` and `outcome`
nodes (spec 006 Graph Behaviour: Move branch).

Each node is a factory closing over `GraphDeps`, wrapped in `traced` so it stays a
plain async function testable through the compiled graph (D2). Classifier output is
normalised deterministically (D8) before routing: an unknown `move_id` forces a
clarification, unknown or duplicate `alternatives` are dropped, and `roll_stat` is
resolved from the move's own stat, overriding the classifier when they disagree.
`clarify` and `no_move` never call an LLM (D10, D16). `roll` and `outcome` run only
when `explain` matched a rolled move and the turn asked for a roll (D6): `roll`
calls `backend.domain.dice.roll` and `outcome` calls `backend.domain.outcome.
resolve_outcome`, appending the result to the move reply's text via
`dataclasses.replace` -- no dice or band logic is re-implemented here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from backend.domain.dice import Band
from backend.domain.dice import roll as roll_dice
from backend.domain.outcome import resolve_outcome
from backend.domain.rulebook import ABILITY_STATS, AbilityStat, Move
from backend.domain.urls import move_url
from backend.graph.deps import GraphDeps
from backend.graph.llm_outputs import (
    NO_MOVE,
    MoveClassification,
    classifier_schema,
    parse_classifier_output,
)
from backend.graph.prompts import (
    CLASSIFIER_SYSTEM,
    EXPLAIN_SYSTEM,
    classifier_user,
    explain_user,
)
from backend.graph.replies import (
    NOT_ROLLED_TEXT,
    clarification_text,
    error_reply,
    no_move_text,
    roll_phrase,
    roll_text_with_modifier,
    roll_text_without_modifier,
)
from backend.graph.state import GraphState, MoveCard, Reply
from backend.graph.tracing import NodeFn, call_llm, traced
from backend.ports.llm import LLMRequest
from backend.ports.tracer import TraceEvent

_CANDIDATE_CATEGORIES = frozenset({"basic", "special"})


def resolve_roll_stat(
    move: Move, classifier_stat: AbilityStat | None
) -> AbilityStat | None:
    if move.stat in ABILITY_STATS:
        return move.stat
    if move.stat == "VARIES":
        return classifier_stat
    return None


def _candidates(deps: GraphDeps) -> tuple[Move, ...]:
    return tuple(
        move
        for move in deps.rulebook.list_moves()
        if move.category in _CANDIDATE_CATEGORIES
    )


def make_classify_move(deps: GraphDeps) -> NodeFn:
    async def classify_move(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        candidates = _candidates(deps)
        candidates_by_id = {move.id: move for move in candidates}

        request = LLMRequest(
            role="classifier",
            system=CLASSIFIER_SYSTEM,
            user=classifier_user(turn.message, candidates),
            max_tokens=deps.settings.classifier_max_tokens,
            temperature=0.0,
            response_schema=classifier_schema([move.id for move in candidates]),
            schema_name="move_classification",
        )
        result = await call_llm(deps, state, "classify_move", request)
        if isinstance(result, Reply):
            return {"candidates": candidates, "reply": result}

        try:
            parsed = parse_classifier_output(result.text)
        except ValueError as exc:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="classify_move",
                    name="llm_output_invalid",
                    attributes={"error": str(exc)},
                )
            )
            return {"candidates": candidates, "reply": error_reply()}

        move_id = parsed.move_id
        confidence = parsed.confidence
        stat = parsed.stat

        if move_id != NO_MOVE and move_id not in candidates_by_id:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="classify_move",
                    name="classifier_unknown_move",
                    attributes={"move_id": move_id},
                )
            )
            move_id = NO_MOVE
            confidence = 0.0

        seen: set[str] = set()
        kept: list[str] = []
        dropped: list[str] = []
        for alternative in parsed.alternatives:
            if alternative == move_id:
                continue
            if alternative != NO_MOVE and alternative not in candidates_by_id:
                if alternative not in dropped:
                    dropped.append(alternative)
                continue
            if alternative in seen:
                continue
            seen.add(alternative)
            kept.append(alternative)
        if dropped:
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="classify_move",
                    name="classifier_alternatives_stripped",
                    attributes={"ids": ",".join(dropped)},
                )
            )

        classification = MoveClassification(
            move_id=move_id,
            confidence=confidence,
            stat=stat,
            rationale=parsed.rationale,
            alternatives=tuple(kept),
        )

        output: dict[str, object] = {
            "candidates": candidates,
            "classification": classification,
        }

        matched_move = candidates_by_id.get(move_id)
        if matched_move is not None:
            matched_roll_stat = resolve_roll_stat(matched_move, stat)
            if stat != matched_roll_stat:
                deps.tracer.record_event(
                    TraceEvent(
                        trace_id=turn.trace_id,
                        session_id=turn.session_id,
                        node="classify_move",
                        name="classifier_stat_overridden",
                        attributes={
                            "classifier_stat": stat,
                            "move_stat": matched_roll_stat,
                        },
                    )
                )
            output["move"] = matched_move
            output["roll_stat"] = matched_roll_stat

        return output

    return traced("classify_move", deps, classify_move)


def make_clarify(deps: GraphDeps) -> NodeFn:
    async def clarify(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        classification = state.get("classification")
        if classification is None:
            raise RuntimeError("clarify reached without a classification")
        candidates_by_id = {move.id: move for move in state.get("candidates", ())}
        option_ids = (classification.move_id, *classification.alternatives)[:3]
        options: list[Move | str] = [
            candidates_by_id.get(option_id, NO_MOVE) for option_id in option_ids
        ]
        deps.tracer.record_event(
            TraceEvent(
                trace_id=turn.trace_id,
                session_id=turn.session_id,
                node="clarify",
                name="clarification_requested",
                attributes={"confidence": classification.confidence},
            )
        )
        return {"reply": Reply(kind="clarification", text=clarification_text(options))}

    return traced("clarify", deps, clarify)


def make_no_move(deps: GraphDeps) -> NodeFn:
    async def no_move(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        classification = state.get("classification")
        if classification is None:
            raise RuntimeError("no_move reached without a classification")
        text = no_move_text(classification.rationale, turn.roll_requested)
        return {"reply": Reply(kind="no_move", text=text)}

    return traced("no_move", deps, no_move)


def make_explain(deps: GraphDeps) -> NodeFn:
    async def explain(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        move = state.get("move")
        if move is None:
            raise RuntimeError("explain reached without a matched move")
        roll_stat = state.get("roll_stat")
        classification = state.get("classification")
        if classification is None:
            raise RuntimeError("explain reached without a classification")
        phrase = roll_phrase(move, roll_stat)

        request = LLMRequest(
            role="answer",
            system=EXPLAIN_SYSTEM,
            user=explain_user(turn.message, move, phrase, classification.rationale),
            max_tokens=deps.settings.explain_max_tokens,
            temperature=deps.settings.answer_temperature,
        )
        result = await call_llm(deps, state, "explain", request)
        if isinstance(result, Reply):
            return {"reply": result}

        if not result.text.strip():
            deps.tracer.record_event(
                TraceEvent(
                    trace_id=turn.trace_id,
                    session_id=turn.session_id,
                    node="explain",
                    name="llm_output_invalid",
                    attributes={"error": "explanation is empty"},
                )
            )
            return {"reply": error_reply()}

        text = result.text
        if turn.roll_requested and not move.is_rolled:
            text = f"{text}\n\n{NOT_ROLLED_TEXT.format(name=move.name)}"

        card = MoveCard(
            move_id=move.id,
            name=move.name,
            url=move_url(move.id),
            trigger=move.trigger,
            stat=move.stat,
            roll_stat=roll_stat,
            outcomes=move.outcomes,
        )
        return {"reply": Reply(kind="move", text=text, move=card)}

    return traced("explain", deps, explain)


def make_roll(deps: GraphDeps) -> NodeFn:
    async def roll(state: GraphState) -> Mapping[str, object]:
        turn = state["turn"]
        rolled = roll_dice(deps.rng, turn.modifier)
        return {"roll": rolled}

    return traced("roll", deps, roll)


def make_outcome(deps: GraphDeps) -> NodeFn:
    async def outcome(state: GraphState) -> Mapping[str, object]:
        move = state.get("move")
        rolled = state.get("roll")
        reply = state.get("reply")
        if move is None or rolled is None or reply is None or reply.move is None:
            raise RuntimeError("outcome reached without a move, roll and reply")
        card = reply.move

        if rolled.modifier is not None:
            resolved = resolve_outcome(move, rolled)
            new_card = replace(card, roll=rolled, outcome=resolved)
            text = f"{reply.text}\n\n{roll_text_with_modifier(rolled)}"
        else:
            bands: tuple[tuple[int, Band], ...] = tuple(
                (modifier, rolled.band_with(modifier)) for modifier in range(-3, 4)
            )
            new_card = replace(card, roll=rolled, bands_by_modifier=bands)
            text = f"{reply.text}\n\n{roll_text_without_modifier(rolled)}"

        return {"reply": replace(reply, text=text, move=new_card)}

    return traced("outcome", deps, outcome)
