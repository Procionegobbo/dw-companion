"""Tests for `evals/runner.py`: rule R-LABEL's second enforcement point and the
runner's core behaviour, built on spec 006's fakes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from backend.adapters.openrouter import ModelPrice
from backend.adapters.tee_tracer import TeeTracer
from backend.graph.builder import Assistant
from backend.graph.deps import GraphSettings
from backend.graph.state import Reply, TurnInput, TurnResult
from backend.ports.errors import PortError
from backend.ports.llm import ModelRole
from backend.ports.retriever import RetrievedChunk
from backend.ports.tracer import Tracer
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.tracer import FakeTracer
from backend.tests.graph_helpers import (
    chunk,
    classifier_json,
    make_assistant,
    router_json,
)
from evals.collector import CollectingTracer
from evals.config import EvalConfig, EvalModels
from evals.datasets import (
    Case,
    Dataset,
    DatasetName,
    MoveCase,
    RouterCase,
    RulesCase,
    UnreviewedRowsError,
)
from evals.runner import RunOutcome, run_datasets

from .helpers import CostingLLMClient

_MODELS = EvalModels(
    router="m-router",
    classifier="m-classifier",
    answer="m-answer",
    embeddings="m-embeddings",
    judge="m-judge",
)


def _config(graph: GraphSettings | None = None) -> EvalConfig:
    return EvalConfig(
        name="test",
        sha256="x",
        models=_MODELS,
        graph=graph if graph is not None else GraphSettings(),
    )


def _generous_prices() -> dict[str, ModelPrice]:
    price = ModelPrice(prompt_usd_per_token=1e-6, completion_usd_per_token=2e-6)
    return {
        "m-router": price,
        "m-classifier": price,
        "m-answer": price,
        "m-judge": price,
    }


def _zero_prices() -> dict[str, ModelPrice]:
    price = ModelPrice(prompt_usd_per_token=0.0, completion_usd_per_token=0.0)
    return {
        "m-router": price,
        "m-classifier": price,
        "m-answer": price,
        "m-judge": price,
    }


def _dataset(name: DatasetName, cases: Sequence[Case]) -> Dataset:
    return Dataset(
        name=name, path=Path(f"{name}.jsonl"), sha256="x", cases=tuple(cases)
    )


def _id_sequence(prefix: str = "trace") -> Callable[[], str]:
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"{prefix}-{counter['n']}"

    return new_id


def _counting_clock() -> Callable[[], float]:
    calls = {"n": 0}

    def clock() -> float:
        calls["n"] += 1
        return calls["n"] * 0.25

    return clock


def _build(
    llm_script: dict[ModelRole, list[str | PortError]],
    judge_script: list[str | PortError],
    *,
    chunks: Sequence[RetrievedChunk] = (),
    graph_settings: GraphSettings | None = None,
) -> tuple[
    Assistant, TeeTracer, CollectingTracer, FakeLLMClient, FakeLLMClient, FakeTracer
]:
    fake_tracer = FakeTracer()
    collector = CollectingTracer()
    tee = TeeTracer(fake_tracer, collector)
    llm = FakeLLMClient(llm_script)
    assistant, _ = make_assistant(
        llm,
        retriever=FakeRetriever(chunks),
        tracer=tee,
        settings=graph_settings if graph_settings is not None else GraphSettings(),
    )
    judge = FakeLLMClient({"answer": judge_script})
    return assistant, tee, collector, llm, judge, fake_tracer


def _run(
    datasets: Sequence[Dataset],
    assistant: Assistant,
    tracer: Tracer,
    collector: CollectingTracer,
    judge: FakeLLMClient,
    *,
    prices: dict[str, ModelPrice] | None = None,
    budget_usd: float = 100.0,
    graph_settings: GraphSettings | None = None,
) -> RunOutcome:
    return asyncio.run(
        run_datasets(
            datasets,
            config=_config(graph_settings),
            assistant=assistant,
            tracer=tracer,
            collector=collector,
            judge=judge,
            prices=prices if prices is not None else _generous_prices(),
            budget_usd=budget_usd,
            run_id="run-1",
            new_id=_id_sequence(),
            clock=_counting_clock(),
            progress=lambda _line: None,
        )
    )


class _RecordingAssistant(Assistant):
    """A stub `Assistant` that returns a fixed `TurnResult` and remembers every
    `TurnInput` it was given, so a test can inspect what the runner built
    without running the real graph."""

    def __init__(self, result: TurnResult) -> None:
        super().__init__(compiled=None)
        self._result = result
        self.turns: list[TurnInput] = []

    async def run(self, turn: TurnInput) -> TurnResult:
        self.turns.append(turn)
        return self._result


def test_run_datasets_refuses_unreviewed_before_any_call() -> None:
    assistant, tee, collector, llm, judge, fake_tracer = _build(
        {"router": [router_json("rules_question")]}, []
    )
    dataset = _dataset(
        "router",
        [
            RouterCase(
                id="router-001",
                message="m",
                expected_intent="rules_question",
                reviewed=False,
            )
        ],
    )

    with pytest.raises(UnreviewedRowsError):
        _run([dataset], assistant, tee, collector, judge)

    assert llm.requests == []
    assert judge.requests == []
    assert fake_tracer.nodes == []
    assert fake_tracer.generations == []
    assert fake_tracer.events == []


def test_router_case_end_to_end() -> None:
    assistant, tee, collector, _llm, judge, _fake_tracer = _build(
        {"router": [router_json("rules_question", confidence=0.9)]}, []
    )
    dataset = _dataset(
        "router",
        [
            RouterCase(
                id="router-001",
                message="Can I Defy Danger here?",
                expected_intent="rules_question",
                reviewed=True,
            )
        ],
    )

    outcome = _run([dataset], assistant, tee, collector, judge)

    records = outcome.records["router"]
    assert len(records) == 1
    record = records[0]
    assert record.result.intent == "rules_question"
    assert record.latency_ms == pytest.approx(250.0)
    assert record.events[0].name == "eval_case"
    assert record.events[0].attributes == {"case_id": "router-001", "dataset": "router"}
    assert record.turn_generations[0].session_id == "run-1"


def test_rules_case_runs_judge_only_for_rules_answer() -> None:
    # Case 1: answerable, retrieval hits, the answer cites it -> kind rules_answer.
    answer_text = "You roll 2d6 with no stat added. [[moves/last-breath]]"
    judge_output = json.dumps(
        {"facts": [{"index": 0, "present": True, "evidence": "roll 2d6"}]}
    )
    assistant1, tee1, collector1, _llm1, judge1, _tracer1 = _build(
        {"router": [router_json("rules_question")], "answer": [answer_text]},
        [judge_output],
        chunks=[chunk("moves/last-breath")],
    )
    answerable_hit = _dataset(
        "rules_qa",
        [
            RulesCase(
                id="rules-001",
                message="What happens on Last Breath?",
                expected_section_ids=("moves/last-breath",),
                key_facts=("You roll 2d6 with no stat added",),
                reviewed=True,
            )
        ],
    )
    outcome1 = _run([answerable_hit], assistant1, tee1, collector1, judge1)
    assert len(judge1.requests) == 1
    record1 = outcome1.records["rules_qa"][0]
    assert record1.result.reply.kind == "rules_answer"
    assert record1.verdicts is not None

    # Case 2 (answerable, empty retrieval -> rules_not_found) and case 3
    # (unanswerable) both run through an empty-retriever assistant and must
    # never call the judge; an unscripted judge call raises loudly.
    assistant2, tee2, collector2, _llm2, judge2, _tracer2 = _build(
        {"router": [router_json("rules_question"), router_json("rules_question")]},
        [],
        chunks=(),
    )
    empty_retrieval = _dataset(
        "rules_qa",
        [
            RulesCase(
                id="rules-002",
                message="What happens on Last Breath?",
                expected_section_ids=("moves/last-breath",),
                key_facts=("You roll 2d6 with no stat added",),
                reviewed=True,
            ),
            RulesCase(
                id="rules-003",
                message="How many spell slots does a wizard have?",
                expected_section_ids=(),
                key_facts=(),
                reviewed=True,
            ),
        ],
    )
    outcome2 = _run([empty_retrieval], assistant2, tee2, collector2, judge2)
    assert judge2.requests == []
    kinds = [record.result.reply.kind for record in outcome2.records["rules_qa"]]
    assert kinds == ["rules_not_found", "rules_not_found"]
    assert all(record.verdicts is None for record in outcome2.records["rules_qa"])


def test_move_case_uses_normalised_classification() -> None:
    assistant, tee, collector, _llm, judge, _tracer = _build(
        {
            "router": [router_json("action_description")],
            "classifier": [classifier_json("not-a-real-move", confidence=0.9)],
        },
        [],
    )
    dataset = _dataset(
        "move_classification",
        [
            MoveCase(
                id="move-001",
                message="I swing my axe at the orc.",
                expected_move_id="hack-and-slash",
                acceptable_alternatives=(),
                reviewed=True,
            )
        ],
    )

    outcome = _run([dataset], assistant, tee, collector, judge)

    record = outcome.records["move_classification"][0]
    assert record.result.classification is not None
    assert record.result.classification.move_id == "no_move"
    assert record.result.reply.kind == "clarification"


def test_turns_never_roll() -> None:
    fixed_result = TurnResult(
        reply=Reply(kind="out_of_scope", text="x"),
        intent=None,
        router_confidence=None,
        classification=None,
        retrieved_section_ids=(),
    )
    assistant = _RecordingAssistant(fixed_result)
    collector = CollectingTracer()
    dataset = _dataset(
        "router",
        [
            RouterCase(
                id=f"router-{i:03d}",
                message="m",
                expected_intent="out_of_scope",
                reviewed=True,
            )
            for i in range(1, 4)
        ],
    )

    _run([dataset], assistant, collector, collector, FakeLLMClient({"answer": []}))

    assert len(assistant.turns) == 3
    assert all(turn.roll_requested is False for turn in assistant.turns)


def test_inflight_backstop_aborts() -> None:
    llm = CostingLLMClient(
        FakeLLMClient(
            {
                "router": [
                    router_json("out_of_scope"),
                    router_json("out_of_scope"),
                    router_json("out_of_scope"),
                ]
            }
        ),
        cost=5.0,
    )
    fake_tracer = FakeTracer()
    collector = CollectingTracer()
    tee = TeeTracer(fake_tracer, collector)
    assistant, _ = make_assistant(llm, retriever=FakeRetriever(()), tracer=tee)
    judge = FakeLLMClient({"answer": []})

    dataset = _dataset(
        "router",
        [
            RouterCase(
                id=f"router-{i:03d}",
                message="m",
                expected_intent="out_of_scope",
                reviewed=True,
            )
            for i in range(1, 4)
        ],
    )

    outcome = _run(
        [dataset],
        assistant,
        tee,
        collector,
        judge,
        prices=_zero_prices(),
        budget_usd=6.0,
    )

    assert outcome.aborted is True
    assert len(outcome.records["router"]) == 2
    assert outcome.spent_usd == pytest.approx(10.0)


def test_cases_run_in_file_order() -> None:
    assistant, tee, collector, _llm, judge, _tracer = _build(
        {
            "router": [
                router_json("rules_question"),
                router_json("action_description"),
            ],
            "classifier": [classifier_json("no_move", confidence=0.9)],
        },
        [],
    )
    router_dataset = _dataset(
        "router",
        [
            RouterCase(
                id="router-001",
                message="m1",
                expected_intent="rules_question",
                reviewed=True,
            )
        ],
    )
    move_dataset = _dataset(
        "move_classification",
        [
            MoveCase(
                id="move-001",
                message="m2",
                expected_move_id="no_move",
                acceptable_alternatives=(),
                reviewed=True,
            )
        ],
    )

    outcome = _run([router_dataset, move_dataset], assistant, tee, collector, judge)

    assert [r.case.id for r in outcome.records["router"]] == ["router-001"]
    assert [r.case.id for r in outcome.records["move_classification"]] == ["move-001"]
