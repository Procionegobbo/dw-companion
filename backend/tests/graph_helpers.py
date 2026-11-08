"""Shared fixtures and builders for `backend/tests/test_graph_*.py`.

Not collected by pytest (no `test_` prefix). `MOVES` is the six spec 005 fixture
moves (plus `make-camp`); `chunk`, `router_json` and `classifier_json` build port
value objects / scripted LLM text; `make_assistant` builds an `Assistant` wired to
fakes, with a clock that advances 0.01s per call so latencies are deterministic;
`turn` builds a `TurnInput` with fixed `session_id`/`trace_id`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import overload

from backend.domain.dice import RandomSource
from backend.domain.rulebook import AbilityStat, Move, move_from_dict
from backend.domain.urls import section_url
from backend.graph.builder import Assistant, build_assistant
from backend.graph.deps import GraphDeps, GraphSettings
from backend.graph.llm_outputs import Intent
from backend.graph.state import TurnInput
from backend.ports.llm import LLMClient
from backend.ports.retriever import ChunkType, RetrievedChunk, Retriever
from backend.ports.rulebook import RulebookRepository
from backend.ports.tracer import Tracer
from backend.tests.domain_helpers import (
    DEFY_DANGER,
    DISCERN_REALITIES,
    HACK_AND_SLASH,
    LAST_BREATH,
    MAKE_CAMP,
    VOLLEY,
    ScriptedRandom,
)
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.rulebook import FakeRulebookRepository
from backend.tests.fakes.tracer import FakeTracer

MOVES: tuple[Move, ...] = tuple(
    move_from_dict(fixture)
    for fixture in (
        HACK_AND_SLASH,
        DEFY_DANGER,
        VOLLEY,
        DISCERN_REALITIES,
        LAST_BREATH,
        MAKE_CAMP,
    )
)


def chunk(
    section_id: str,
    *,
    title: str = "Title",
    type: ChunkType = "section",
    chapter: str | None = None,
    text: str = "text",
    score: float = 1.0,
) -> RetrievedChunk:
    resolved_chapter = chapter if chapter is not None else section_id.split("/", 1)[0]
    return RetrievedChunk(
        section_id=section_id,
        title=title,
        chapter=resolved_chapter,
        anchor_url=section_url(section_id),
        type=type,
        text=text,
        score=score,
    )


def router_json(intent: Intent, confidence: float = 0.9) -> str:
    return json.dumps({"intent": intent, "confidence": confidence})


def classifier_json(
    move_id: str,
    confidence: float = 0.9,
    stat: AbilityStat | None = None,
    rationale: str = "r",
    alternatives: Sequence[str] = (),
) -> str:
    return json.dumps(
        {
            "move_id": move_id,
            "confidence": confidence,
            "stat": stat,
            "rationale": rationale,
            "alternatives": list(alternatives),
        }
    )


def _fake_clock() -> Callable[[], float]:
    calls = {"n": 0}

    def clock() -> float:
        calls["n"] += 1
        return calls["n"] * 0.01

    return clock


@overload
def make_assistant(
    llm: LLMClient,
    *,
    retriever: Retriever | None = None,
    rulebook: RulebookRepository | None = None,
    rng: RandomSource | None = None,
    tracer: FakeTracer | None = None,
    settings: GraphSettings | None = None,
) -> tuple[Assistant, FakeTracer]: ...


@overload
def make_assistant(
    llm: LLMClient,
    *,
    retriever: Retriever | None = None,
    rulebook: RulebookRepository | None = None,
    rng: RandomSource | None = None,
    tracer: Tracer,
    settings: GraphSettings | None = None,
) -> tuple[Assistant, Tracer]: ...


def make_assistant(
    llm: LLMClient,
    *,
    retriever: Retriever | None = None,
    rulebook: RulebookRepository | None = None,
    rng: RandomSource | None = None,
    tracer: Tracer | None = None,
    settings: GraphSettings | None = None,
) -> tuple[Assistant, Tracer]:
    resolved_tracer = tracer if tracer is not None else FakeTracer()
    deps = GraphDeps(
        llm=llm,
        retriever=retriever if retriever is not None else FakeRetriever(),
        tracer=resolved_tracer,
        rulebook=rulebook if rulebook is not None else FakeRulebookRepository(MOVES),
        rng=rng if rng is not None else ScriptedRandom([]),
        settings=settings if settings is not None else GraphSettings(),
        clock=_fake_clock(),
    )
    return build_assistant(deps), resolved_tracer


def turn(
    message: str = "m",
    *,
    roll_requested: bool = False,
    modifier: int | None = None,
) -> TurnInput:
    return TurnInput(
        message=message,
        session_id="s1",
        trace_id="t1",
        roll_requested=roll_requested,
        modifier=modifier,
    )
