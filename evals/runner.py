"""The eval runner core (spec 009 *Tracing* -> "Per case, the runner", *Budget
Guard* in-flight backstop).

`run_datasets` is rule R-LABEL's **second** enforcement point (D1): its first
statement re-checks every selected dataset, independently of whatever gate
`evals/run.py`'s `main` already ran, so a programmatic caller that bypasses
`main` still cannot run unreviewed rows. Every turn runs end to end through
the `Assistant` with `roll_requested=False` (D3): rolling is deterministic
code and is not under eval.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from backend.adapters.openrouter import ModelPrice
from backend.graph.builder import Assistant
from backend.graph.state import TurnInput, TurnResult
from backend.ports.llm import LLMClient
from backend.ports.tracer import GenerationTrace, TraceEvent, Tracer
from evals.budget import case_bound, generation_cost
from evals.collector import CollectingTracer
from evals.config import EvalConfig
from evals.datasets import Case, Dataset, DatasetName, RulesCase, ensure_reviewed
from evals.judge import JUDGE_NODE, FactVerdict, JudgeError, judge_key_facts


@dataclass(frozen=True, slots=True)
class CaseRecord:
    dataset: DatasetName
    case: Case
    trace_id: str
    result: TurnResult
    latency_ms: float
    turn_generations: tuple[GenerationTrace, ...]
    events: tuple[TraceEvent, ...]
    verdicts: tuple[FactVerdict, ...] | None
    judge_error: str | None
    judge_generations: tuple[GenerationTrace, ...]


@dataclass(frozen=True, slots=True)
class RunOutcome:
    records: dict[DatasetName, list[CaseRecord]]
    aborted: bool
    spent_usd: float
    unknown_cost_calls: int


def _needs_judge(dataset: Dataset, case: Case, result: TurnResult) -> bool:
    return (
        dataset.name == "rules_qa"
        and isinstance(case, RulesCase)
        and case.answerable
        and result.reply.kind == "rules_answer"
    )


async def run_datasets(
    datasets: Sequence[Dataset],
    *,
    config: EvalConfig,
    assistant: Assistant,
    tracer: Tracer,
    collector: CollectingTracer,
    judge: LLMClient,
    prices: Mapping[str, ModelPrice],
    budget_usd: float,
    run_id: str,
    new_id: Callable[[], str],
    clock: Callable[[], float],
    progress: Callable[[str], None],
) -> RunOutcome:
    for dataset in datasets:
        ensure_reviewed(dataset)

    records: dict[DatasetName, list[CaseRecord]] = {
        dataset.name: [] for dataset in datasets
    }
    spent_usd = 0.0
    unknown_cost_calls = 0
    aborted = False

    for dataset in datasets:
        if aborted:
            break
        for case in dataset.cases:
            bound = case_bound(dataset.name, case, config, prices)
            if spent_usd + bound > budget_usd:
                aborted = True
                break

            trace_id = new_id()
            tracer.record_event(
                TraceEvent(
                    trace_id=trace_id,
                    session_id=run_id,
                    node="eval",
                    name="eval_case",
                    attributes={"case_id": case.id, "dataset": dataset.name},
                )
            )

            turn = TurnInput(
                message=case.message,
                session_id=run_id,
                trace_id=trace_id,
                roll_requested=False,
            )
            start = clock()
            result = await assistant.run(turn)
            end = clock()
            latency_ms = (end - start) * 1000

            verdicts: tuple[FactVerdict, ...] | None = None
            judge_error: str | None = None
            if isinstance(case, RulesCase) and _needs_judge(dataset, case, result):
                try:
                    verdicts = await judge_key_facts(
                        judge,
                        tracer,
                        clock,
                        trace_id=trace_id,
                        session_id=run_id,
                        question=case.message,
                        answer=result.reply.text,
                        key_facts=case.key_facts,
                    )
                except JudgeError as exc:
                    judge_error = str(exc)

            trace_records = collector.take(trace_id)
            turn_generations = tuple(
                g for g in trace_records.generations if g.node != JUDGE_NODE
            )
            judge_generations = tuple(
                g for g in trace_records.generations if g.node == JUDGE_NODE
            )

            for generation in trace_records.generations:
                cost, unknown = generation_cost(generation)
                spent_usd += cost
                if unknown:
                    unknown_cost_calls += 1

            records[dataset.name].append(
                CaseRecord(
                    dataset=dataset.name,
                    case=case,
                    trace_id=trace_id,
                    result=result,
                    latency_ms=latency_ms,
                    turn_generations=turn_generations,
                    events=trace_records.events,
                    verdicts=verdicts,
                    judge_error=judge_error,
                    judge_generations=judge_generations,
                )
            )

        if not aborted:
            progress(
                f"{dataset.name} done: {len(records[dataset.name])} cases, "
                f"spent ${spent_usd:.4f}"
            )

    return RunOutcome(
        records=records,
        aborted=aborted,
        spent_usd=spent_usd,
        unknown_cost_calls=unknown_cost_calls,
    )
