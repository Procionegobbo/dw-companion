"""Tests for `evals/metrics.py` (spec 009 *Metrics*): pure, hand-built
`CaseRecord`s, no fakes and no async."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from backend.graph.llm_outputs import Intent, MoveClassification
from backend.graph.state import Citation, Reply, ReplyKind, TurnResult
from backend.ports.llm import LLMRequest, LLMResponse
from backend.ports.tracer import AttributeValue, GenerationTrace, TraceEvent
from evals.datasets import MoveCase, RouterCase, RulesCase
from evals.judge import FactVerdict
from evals.metrics import (
    move_metrics,
    percentile,
    rate,
    recall_at_k,
    router_metrics,
    rules_metrics,
    system_metrics,
)
from evals.runner import CaseRecord

_REQUEST = LLMRequest(
    role="answer", system="s", user="u", max_tokens=10, temperature=0.0
)


def _generation(
    node: str,
    *,
    input_tokens: int = 10,
    output_tokens: int = 5,
    cost_usd: float | None = 0.001,
) -> GenerationTrace:
    response = LLMResponse(
        text="t",
        model="m",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
    return GenerationTrace(
        trace_id="t",
        session_id="s",
        node=node,
        request=_REQUEST,
        response=response,
        latency_ms=1.0,
    )


def _event(name: str, attributes: Mapping[str, AttributeValue]) -> TraceEvent:
    return TraceEvent(
        trace_id="t",
        session_id="s",
        node="citation_validator",
        name=name,
        attributes=attributes,
    )


def _router_record(
    expected_intent: Intent, predicted_intent: Intent | None
) -> CaseRecord:
    case = RouterCase(
        id="router-x", message="m", expected_intent=expected_intent, reviewed=True
    )
    result = TurnResult(
        reply=Reply(kind="out_of_scope", text="x"),
        intent=predicted_intent,
        router_confidence=0.9,
        classification=None,
        retrieved_section_ids=(),
    )
    return CaseRecord(
        dataset="router",
        case=case,
        trace_id="t",
        result=result,
        latency_ms=10.0,
        turn_generations=(),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(),
    )


def test_rate_and_percentile() -> None:
    assert rate(1, 0) is None
    assert percentile([], 50) is None
    assert percentile([5], 95) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile(list(range(1, 21)), 95) == pytest.approx(19.05)


def test_router_accuracy_and_confusion() -> None:
    records = [
        _router_record("rules_question", "rules_question"),
        _router_record("action_description", "action_description"),
        _router_record("out_of_scope", "out_of_scope"),
        _router_record("rules_question", None),
    ]
    metrics = router_metrics(records)
    assert metrics["accuracy"] == 0.75
    matrix = cast("dict[str, dict[str, int]]", metrics["confusion_matrix"])
    assert matrix["rules_question"]["error"] == 1
    assert "error" not in matrix.get("action_description", {})
    assert "error" not in matrix.get("out_of_scope", {})


def test_recall_at_k() -> None:
    assert recall_at_k({"a", "b"}, ["b", "c"]) == 0.5
    assert recall_at_k({"a", "b"}, []) == 0.0


def _rules_record(
    *,
    expected_section_ids: Sequence[str] = (),
    key_facts: Sequence[str] = (),
    reply: Reply,
    retrieved: Sequence[str] = (),
    generations: Sequence[GenerationTrace] = (),
    events: Sequence[TraceEvent] = (),
    verdicts: tuple[FactVerdict, ...] | None = None,
    judge_error: str | None = None,
    intent: Intent | None = "rules_question",
) -> CaseRecord:
    case = RulesCase(
        id="rules-x",
        message="m",
        expected_section_ids=tuple(expected_section_ids),
        key_facts=tuple(key_facts),
        reviewed=True,
    )
    result = TurnResult(
        reply=reply,
        intent=intent,
        router_confidence=0.9,
        classification=None,
        retrieved_section_ids=tuple(retrieved),
    )
    return CaseRecord(
        dataset="rules_qa",
        case=case,
        trace_id="t",
        result=result,
        latency_ms=10.0,
        turn_generations=tuple(generations),
        events=tuple(events),
        verdicts=verdicts,
        judge_error=judge_error,
        judge_generations=(),
    )


def test_rules_citation_validity() -> None:
    two_valid_one_stripped = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1"],
        reply=Reply(
            kind="rules_answer",
            text="t",
            citations=(
                Citation(section_id="s1", title="T1", url="/u1"),
                Citation(section_id="s2", title="T2", url="/u2"),
            ),
        ),
        retrieved=["s1", "s2"],
        generations=[_generation("answer_with_citations")],
        events=[_event("citations_stripped", {"count": 1})],
    )
    zero_and_zero = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1"],
        reply=Reply(kind="rules_answer", text="t"),
        retrieved=["s1"],
        generations=[_generation("answer_with_citations")],
    )
    not_found_after_no_valid_citation = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1"],
        reply=Reply(kind="rules_not_found", text="t"),
        retrieved=["s1"],
        generations=[_generation("answer_with_citations")],
        events=[_event("citations_stripped", {"count": 2})],
    )

    metrics = rules_metrics(
        [two_valid_one_stripped, zero_and_zero, not_found_after_no_valid_citation],
        retrieval_k=6,
    )
    assert metrics["citation_validity_rate"] == pytest.approx(2 / 5)
    assert metrics["answers_without_citations"] == 1


def test_rules_refusal_rate_and_misrouted() -> None:
    answerable_hit = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f"],
        reply=Reply(kind="rules_answer", text="t"),
        retrieved=["s1"],
    )
    unanswerable_refused = _rules_record(
        reply=Reply(kind="rules_not_found", text="t"),
    )
    unanswerable_wrong = _rules_record(
        reply=Reply(kind="rules_answer", text="t"),
    )
    misrouted = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f"],
        reply=Reply(kind="rules_answer", text="t"),
        retrieved=["s1"],
        intent="action_description",
    )

    metrics = rules_metrics(
        [answerable_hit, unanswerable_refused, unanswerable_wrong, misrouted],
        retrieval_k=6,
    )
    assert metrics["correct_refusal_rate"] == pytest.approx(0.5)
    assert metrics["misrouted"] == 1


def test_key_fact_coverage_excludes_judge_errors_and_scores_non_answers_zero() -> None:
    judged = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1", "f2"],
        reply=Reply(kind="rules_answer", text="t"),
        retrieved=["s1"],
        verdicts=(
            FactVerdict(index=0, fact="f1", present=True, evidence="e"),
            FactVerdict(index=1, fact="f2", present=False, evidence=""),
        ),
    )
    judge_error_case = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1"],
        reply=Reply(kind="rules_answer", text="t"),
        retrieved=["s1"],
        judge_error="boom",
    )
    non_answer = _rules_record(
        expected_section_ids=["s1"],
        key_facts=["f1"],
        reply=Reply(kind="rules_not_found", text="t"),
        retrieved=[],
    )

    metrics = rules_metrics([judged, judge_error_case, non_answer], retrieval_k=6)
    assert metrics["judge_errors"] == 1
    assert metrics["key_fact_judged_n"] == 2
    assert metrics["key_fact_coverage"] == pytest.approx(0.25)


def _move_record(
    expected_move_id: str,
    acceptable_alternatives: Sequence[str],
    predicted_move_id: str | None,
    *,
    kind: ReplyKind = "move",
    intent: Intent | None = "action_description",
) -> CaseRecord:
    case = MoveCase(
        id="move-x",
        message="m",
        expected_move_id=expected_move_id,
        acceptable_alternatives=tuple(acceptable_alternatives),
        reviewed=True,
    )
    classification = (
        MoveClassification(
            move_id=predicted_move_id,
            confidence=0.9,
            stat=None,
            rationale="r",
            alternatives=(),
        )
        if predicted_move_id is not None
        else None
    )
    result = TurnResult(
        reply=Reply(kind=kind, text="t"),
        intent=intent,
        router_confidence=0.9,
        classification=classification,
        retrieved_section_ids=(),
    )
    return CaseRecord(
        dataset="move_classification",
        case=case,
        trace_id="t",
        result=result,
        latency_ms=5.0,
        turn_generations=(),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(),
    )


def test_move_accuracy_counts_alternatives() -> None:
    record = _move_record("hack-and-slash", ["defy-danger"], "defy-danger")
    metrics = move_metrics([record])
    assert metrics["accuracy"] == 1.0


def test_move_not_routed_is_incorrect_and_in_matrix() -> None:
    record = _move_record("hack-and-slash", [], None)
    metrics = move_metrics([record])
    assert metrics["accuracy"] == 0.0
    matrix = cast("dict[str, dict[str, int]]", metrics["confusion_matrix"])
    assert matrix["hack-and-slash"]["(not routed)"] == 1


def test_no_move_precision_recall() -> None:
    correct_no_move = _move_record("no_move", [], "no_move")
    wrong_predicted_no_move = _move_record("hack-and-slash", [], "no_move")
    missed_no_move = _move_record("no_move", [], "defy-danger")

    metrics = move_metrics([correct_no_move, wrong_predicted_no_move, missed_no_move])
    assert metrics["no_move_precision"] == pytest.approx(0.5)
    assert metrics["no_move_recall"] == pytest.approx(0.5)

    no_no_move_cases = move_metrics(
        [_move_record("hack-and-slash", [], "hack-and-slash")]
    )
    assert no_no_move_cases["no_move_precision"] is None
    assert no_no_move_cases["no_move_recall"] is None


def test_clarification_rate() -> None:
    clarified = _move_record(
        "hack-and-slash", [], "hack-and-slash", kind="clarification"
    )
    not_clarified = _move_record("hack-and-slash", [], "hack-and-slash", kind="move")
    metrics = move_metrics([clarified, not_clarified])
    assert metrics["clarification_rate"] == 0.5


def test_system_metrics_per_intent_excludes_judge_and_unknown_cost() -> None:
    known_cost_record = _router_record("rules_question", "rules_question")
    known_cost_record = CaseRecord(
        dataset=known_cost_record.dataset,
        case=known_cost_record.case,
        trace_id=known_cost_record.trace_id,
        result=known_cost_record.result,
        latency_ms=100.0,
        turn_generations=(_generation("answer_with_citations", cost_usd=0.001),),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(_generation("judge_key_facts", cost_usd=5.0),),
    )
    unknown_cost_record = CaseRecord(
        dataset="router",
        case=RouterCase(
            id="router-y", message="m", expected_intent="rules_question", reviewed=True
        ),
        trace_id="t2",
        result=TurnResult(
            reply=Reply(kind="error", text="x"),
            intent=None,
            router_confidence=None,
            classification=None,
            retrieved_section_ids=(),
        ),
        latency_ms=200.0,
        turn_generations=(_generation("router", cost_usd=None),),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(),
    )

    system = system_metrics([known_cost_record, unknown_cost_record])
    assert set(system.keys()) == {"all", "rules_question", "error"}
    all_bucket = cast("dict[str, object]", system["all"])
    assert all_bucket["n"] == 2
    rules_question_bucket = cast("dict[str, object]", system["rules_question"])
    assert rules_question_bucket["cost_usd_mean"] == pytest.approx(0.001)
    error_bucket = cast("dict[str, object]", system["error"])
    assert error_bucket["cost_unknown_calls"] == 1
    assert error_bucket["cost_usd_mean"] is None
