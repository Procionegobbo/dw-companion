"""The hard budget guard (spec 009 D10, *Budget Guard*).

`case_bound` is a per-case **upper bound** on cost from a fixed token envelope,
never an estimate of the actual prompt. `estimate` sums it over every selected
case for the pre-flight check; `generation_cost` reads a completed call's
actual cost for the in-flight backstop, falling back to
`UNKNOWN_CALL_COST_USD` when the provider reported none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from backend.adapters.openrouter import ModelPrice
from backend.ports.tracer import GenerationTrace
from evals.config import EvalConfig
from evals.datasets import Case, Dataset, DatasetName, RulesCase
from evals.judge import JUDGE_MAX_TOKENS

DEFAULT_BUDGET_USD: Final = 3.0
MAX_BUDGET_USD: Final = 50.0
UNKNOWN_CALL_COST_USD: Final = 0.01

ROUTER_INPUT_TOKENS: Final = 1000
CLASSIFIER_INPUT_TOKENS: Final = 3000
RULES_BASE_INPUT_TOKENS: Final = 2000
CHUNK_INPUT_TOKENS: Final = 1700
EXPLAIN_INPUT_TOKENS: Final = 1500
JUDGE_INPUT_TOKENS: Final = 2500


def call_cost(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * price.prompt_usd_per_token
        + output_tokens * price.completion_usd_per_token
    )


def case_bound(
    dataset: DatasetName,
    case: Case,
    config: EvalConfig,
    prices: Mapping[str, ModelPrice],
) -> float:
    """An upper bound on what resolving `case` can cost, from the fixed token
    envelope above (not the actual prompt length). The bound covers the
    router call plus the worse of the rules branch's answer call or the move
    branch's classifier+explain calls, since either branch may run depending
    on how the router classifies the message. The judge bound is added only
    for an answerable `rules_qa` case (D5: the judge never runs otherwise)."""
    s = config.graph
    m = config.models

    turn_bound = call_cost(
        prices[m.router], ROUTER_INPUT_TOKENS, s.router_max_tokens
    ) + max(
        call_cost(
            prices[m.answer],
            RULES_BASE_INPUT_TOKENS + s.retrieval_k * CHUNK_INPUT_TOKENS,
            s.answer_max_tokens,
        ),
        call_cost(
            prices[m.classifier], CLASSIFIER_INPUT_TOKENS, s.classifier_max_tokens
        )
        + call_cost(prices[m.answer], EXPLAIN_INPUT_TOKENS, s.explain_max_tokens),
    )

    needs_judge = (
        dataset == "rules_qa" and isinstance(case, RulesCase) and case.answerable
    )
    judge_bound = (
        call_cost(prices[m.judge], JUDGE_INPUT_TOKENS, JUDGE_MAX_TOKENS)
        if needs_judge
        else 0.0
    )
    return turn_bound + judge_bound


def estimate(
    datasets: Sequence[Dataset], config: EvalConfig, prices: Mapping[str, ModelPrice]
) -> float:
    return sum(
        case_bound(dataset.name, case, config, prices)
        for dataset in datasets
        for case in dataset.cases
    )


def generation_cost(g: GenerationTrace) -> tuple[float, bool]:
    """A completed generation's actual cost for the in-flight backstop:
    `(cost_usd, False)`, or `(UNKNOWN_CALL_COST_USD, True)` when the provider
    reported none."""
    if g.response.cost_usd is None:
        return UNKNOWN_CALL_COST_USD, True
    return g.response.cost_usd, False
