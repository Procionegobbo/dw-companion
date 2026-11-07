"""Tests for `TurnInput`/`GraphSettings` validation and the no-reply guard
(spec 006 Testing).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast

import pytest

# `_assistant_from_compiled` is the documented test seam for this exact scenario
# (spec 006 Data Model: "test seam for the no-reply guard"), so this cross-module
# access to a module-private name is intentional.
from backend.graph.builder import (
    _assistant_from_compiled,  # pyright: ignore[reportPrivateUsage]
    build_assistant,
)
from backend.graph.deps import GraphDeps, GraphSettings
from backend.graph.state import TurnInput
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.rulebook import FakeRulebookRepository
from backend.tests.fakes.tracer import FakeTracer
from backend.tests.graph_helpers import make_assistant, turn


class _SingleNodeGraph:
    """A minimal stand-in for a compiled LangGraph whose one node returns `{}`.

    `_assistant_from_compiled` only needs an `ainvoke`, so this avoids importing
    `langgraph` outside `builder.py` (D2, open risk (a)).
    """

    async def ainvoke(self, state: Mapping[str, object]) -> Mapping[str, object]:
        return {}


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"message": "   "}, "message"),
        ({"session_id": "   "}, "session_id"),
        ({"modifier": 11}, "modifier"),
        ({"modifier": True}, "modifier"),
    ],
)
def test_turn_input_validation(overrides: dict[str, object], match: str) -> None:
    base: dict[str, object] = {"message": "m", "session_id": "s1", "trace_id": "t1"}
    base.update(overrides)
    with pytest.raises(ValueError, match=match):
        TurnInput(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("modifier", [-10, 10])
def test_turn_input_accepts_modifier_bounds(modifier: int) -> None:
    turn_input = TurnInput(
        message="m", session_id="s1", trace_id="t1", modifier=modifier
    )
    assert turn_input.modifier == modifier


def test_graph_settings_validation() -> None:
    with pytest.raises(ValueError, match="retrieval_k"):
        GraphSettings(retrieval_k=0)
    with pytest.raises(ValueError, match="clarify_threshold"):
        GraphSettings(clarify_threshold=1.5)


def test_graph_settings_defaults_match_d25() -> None:
    settings = GraphSettings()
    assert settings.retrieval_k == 6
    assert settings.closest_sections_limit == 3
    assert settings.clarify_threshold == 0.6
    assert settings.router_max_tokens == 100
    assert settings.classifier_max_tokens == 400
    assert settings.answer_max_tokens == 700
    assert settings.explain_max_tokens == 300
    assert settings.answer_temperature == 0.0


def test_run_without_reply_raises() -> None:
    assistant = _assistant_from_compiled(_SingleNodeGraph())

    with pytest.raises(RuntimeError, match="graph finished without a reply"):
        asyncio.run(assistant.run(turn()))


def test_compiled_graph_has_no_checkpointer() -> None:
    assistant, _ = make_assistant(FakeLLMClient({}))
    assert cast(Any, assistant.compiled).checkpointer is None


def test_build_assistant_also_has_no_checkpointer() -> None:
    # build_assistant goes through the real deps/settings path, not the test seam.
    deps = GraphDeps(
        llm=FakeLLMClient({}),
        retriever=FakeRetriever(),
        tracer=FakeTracer(),
        rulebook=FakeRulebookRepository([]),
        rng=ScriptedRandom([]),
    )
    assistant = build_assistant(deps)
    assert cast(Any, assistant.compiled).checkpointer is None
