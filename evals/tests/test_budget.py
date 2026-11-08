"""Tests for `evals/budget.py`: the cost bound formula and the backstop's
cost reader."""

from __future__ import annotations

from backend.adapters.openrouter import ModelPrice
from backend.graph.deps import GraphSettings
from backend.ports.llm import LLMRequest, LLMResponse
from backend.ports.tracer import GenerationTrace
from evals.budget import (
    CHUNK_INPUT_TOKENS,
    CLASSIFIER_INPUT_TOKENS,
    EXPLAIN_INPUT_TOKENS,
    JUDGE_INPUT_TOKENS,
    ROUTER_INPUT_TOKENS,
    RULES_BASE_INPUT_TOKENS,
    UNKNOWN_CALL_COST_USD,
    call_cost,
    case_bound,
    generation_cost,
)
from evals.config import EvalConfig, EvalModels
from evals.datasets import RouterCase, RulesCase
from evals.judge import JUDGE_MAX_TOKENS

_PRICE = ModelPrice(prompt_usd_per_token=1e-6, completion_usd_per_token=2e-6)
_PRICES: dict[str, ModelPrice] = {
    "m-router": _PRICE,
    "m-classifier": _PRICE,
    "m-answer": _PRICE,
    "m-judge": _PRICE,
}


def _config(graph: GraphSettings | None = None) -> EvalConfig:
    return EvalConfig(
        name="test",
        sha256="x",
        models=EvalModels(
            router="m-router",
            classifier="m-classifier",
            answer="m-answer",
            embeddings="m-embeddings",
            judge="m-judge",
        ),
        graph=graph if graph is not None else GraphSettings(),
    )


def _router_case() -> RouterCase:
    return RouterCase(
        id="router-001", message="m", expected_intent="rules_question", reviewed=True
    )


def _rules_case(*, answerable: bool) -> RulesCase:
    return RulesCase(
        id="rules-001",
        message="m",
        expected_section_ids=("moves/last-breath",) if answerable else (),
        key_facts=("a fact",) if answerable else (),
        reviewed=True,
    )


def _turn_bound(config: EvalConfig) -> float:
    s = config.graph
    return call_cost(_PRICE, ROUTER_INPUT_TOKENS, s.router_max_tokens) + max(
        call_cost(
            _PRICE,
            RULES_BASE_INPUT_TOKENS + s.retrieval_k * CHUNK_INPUT_TOKENS,
            s.answer_max_tokens,
        ),
        call_cost(_PRICE, CLASSIFIER_INPUT_TOKENS, s.classifier_max_tokens)
        + call_cost(_PRICE, EXPLAIN_INPUT_TOKENS, s.explain_max_tokens),
    )


def test_case_bound_formula() -> None:
    config = _config()
    turn_bound = _turn_bound(config)

    assert case_bound("router", _router_case(), config, _PRICES) == turn_bound

    judge_bound = call_cost(_PRICE, JUDGE_INPUT_TOKENS, JUDGE_MAX_TOKENS)
    answerable_bound = case_bound(
        "rules_qa", _rules_case(answerable=True), config, _PRICES
    )
    assert answerable_bound == turn_bound + judge_bound

    unanswerable_bound = case_bound(
        "rules_qa", _rules_case(answerable=False), config, _PRICES
    )
    assert unanswerable_bound == turn_bound


def test_bound_scales_with_retrieval_k() -> None:
    config_small = _config(GraphSettings(retrieval_k=1))
    config_big = _config(GraphSettings(retrieval_k=10))

    small_bound = case_bound(
        "rules_qa", _rules_case(answerable=True), config_small, _PRICES
    )
    big_bound = case_bound(
        "rules_qa", _rules_case(answerable=True), config_big, _PRICES
    )
    assert big_bound > small_bound


def test_generation_cost_unknown_uses_fallback() -> None:
    request = LLMRequest(
        role="answer", system="s", user="u", max_tokens=10, temperature=0.0
    )
    response = LLMResponse(
        text="t", model="m", input_tokens=1, output_tokens=1, cost_usd=None
    )
    generation = GenerationTrace(
        trace_id="t1",
        session_id="s1",
        node="answer_with_citations",
        request=request,
        response=response,
        latency_ms=1.0,
    )
    assert generation_cost(generation) == (UNKNOWN_CALL_COST_USD, True)
