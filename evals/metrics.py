"""Pure metric functions computed from `evals.runner.CaseRecord`s (spec 009 D4,
*Metrics*).

Every function here is pure: no I/O, no randomness, no mutation of its arguments.
`rate` returns `None` on a zero denominator, which becomes JSON `null`. `percentile`
uses linear interpolation between closest ranks (the same as `statistics.quantiles
(method="inclusive")`); a single value is its own percentile. Values returned inside
the aggregate dicts are already rounded per the Report JSON rules: rates and recall
to 4 decimals, USD to 6, milliseconds and token means to 1 (spec 009 *Rounding*);
`rate`/`percentile` themselves stay unrounded so other callers get full precision.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from statistics import fmean
from typing import cast

from evals.datasets import MoveCase, RouterCase, RulesCase
from evals.runner import CaseRecord

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

_ANSWER_CITATIONS_NODE = "answer_with_citations"
_CITATIONS_STRIPPED_EVENT = "citations_stripped"

_SYSTEM_INTENT_ORDER: tuple[str, ...] = (
    "rules_question",
    "action_description",
    "out_of_scope",
    "error",
)


def rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return float(ordered[0])
    rank = (p / 100) * (n - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, n - 1)
    weight = rank - lower_index
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    return lower + weight * (upper - lower)


def confusion_matrix(pairs: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """`expected -> predicted -> count`. A cell that never occurs is simply
    absent (zero cells are never written)."""
    matrix: dict[str, dict[str, int]] = {}
    for expected, predicted in pairs:
        row = matrix.setdefault(expected, {})
        row[predicted] = row.get(predicted, 0) + 1
    return matrix


def recall_at_k(expected: Collection[str], retrieved: Collection[str]) -> float:
    if not expected:
        return 0.0
    overlap = len(set(expected) & set(retrieved))
    return overlap / len(set(expected))


def _round(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def router_metrics(records: Sequence[CaseRecord]) -> dict[str, JsonValue]:
    n = len(records)
    pairs: list[tuple[str, str]] = []
    correct = 0
    for record in records:
        case = record.case
        assert isinstance(case, RouterCase)
        predicted = record.result.intent or "error"
        pairs.append((case.expected_intent, predicted))
        if predicted == case.expected_intent:
            correct += 1
    return cast(
        dict[str, JsonValue],
        {
            "n": n,
            "accuracy": _round(rate(correct, n), 4),
            "confusion_matrix": confusion_matrix(pairs),
        },
    )


def _citation_counts(record: CaseRecord) -> tuple[int, int] | None:
    """`(valid, stripped)` for `record`'s `answer_with_citations` generation,
    or `None` when that node never ran for this case."""
    generation = next(
        (g for g in record.turn_generations if g.node == _ANSWER_CITATIONS_NODE),
        None,
    )
    if generation is None:
        return None
    valid = (
        len(record.result.reply.citations)
        if record.result.reply.kind == "rules_answer"
        else 0
    )
    stripped_event = next(
        (e for e in record.events if e.name == _CITATIONS_STRIPPED_EVENT), None
    )
    stripped = 0
    if stripped_event is not None:
        count = stripped_event.attributes.get("count", 0)
        if isinstance(count, int):
            stripped = count
    return valid, stripped


def _case_key_fact_coverage(record: CaseRecord) -> float | None:
    """A case's per-case key-fact coverage, or `None` for a `judge_error`
    case. Caller restricts this to answerable cases (D5, *Rules QA*)."""
    if record.judge_error is not None:
        return None
    if record.result.reply.kind != "rules_answer":
        return 0.0
    if not record.verdicts:
        return 0.0
    present = sum(1 for verdict in record.verdicts if verdict.present)
    return present / len(record.verdicts)


def rules_metrics(
    records: Sequence[CaseRecord], retrieval_k: int
) -> dict[str, JsonValue]:
    answerable: list[CaseRecord] = []
    unanswerable: list[CaseRecord] = []
    for record in records:
        case = record.case
        assert isinstance(case, RulesCase)
        (answerable if case.answerable else unanswerable).append(record)

    recalls: list[float] = []
    for record in answerable:
        case = record.case
        assert isinstance(case, RulesCase)
        recalls.append(
            recall_at_k(case.expected_section_ids, record.result.retrieved_section_ids)
        )

    citations_valid = 0
    citations_stripped = 0
    answers_without_citations = 0
    for record in records:
        counts = _citation_counts(record)
        if counts is None:
            continue
        valid, stripped = counts
        citations_valid += valid
        citations_stripped += stripped
        if valid + stripped == 0:
            answers_without_citations += 1

    judge_errors = sum(1 for record in answerable if record.judge_error is not None)
    coverages = [
        coverage
        for record in answerable
        if (coverage := _case_key_fact_coverage(record)) is not None
    ]

    correct_refusal = sum(
        1 for record in unanswerable if record.result.reply.kind == "rules_not_found"
    )
    misrouted = sum(1 for record in records if record.result.intent != "rules_question")

    return cast(
        dict[str, JsonValue],
        {
            "n": len(records),
            "answerable_n": len(answerable),
            "unanswerable_n": len(unanswerable),
            "retrieval_k": retrieval_k,
            "recall_at_k": _round(_mean(recalls), 4),
            "citations_valid": citations_valid,
            "citations_stripped": citations_stripped,
            "answers_without_citations": answers_without_citations,
            "citation_validity_rate": _round(
                rate(citations_valid, citations_valid + citations_stripped), 4
            ),
            "key_fact_coverage": _round(_mean(coverages), 4),
            "key_fact_judged_n": len(answerable) - judge_errors,
            "judge_errors": judge_errors,
            "correct_refusal_rate": _round(rate(correct_refusal, len(unanswerable)), 4),
            "misrouted": misrouted,
        },
    )


def move_metrics(records: Sequence[CaseRecord]) -> dict[str, JsonValue]:
    n = len(records)
    pairs: list[tuple[str, str]] = []
    correct = 0
    predicted_no_move = 0
    correct_no_move = 0
    expected_no_move = 0
    clarifications = 0
    misrouted = 0
    for record in records:
        case = record.case
        assert isinstance(case, MoveCase)
        classification = record.result.classification
        predicted = (
            classification.move_id if classification is not None else "(not routed)"
        )
        pairs.append((case.expected_move_id, predicted))
        if (
            predicted == case.expected_move_id
            or predicted in case.acceptable_alternatives
        ):
            correct += 1
        if predicted == "no_move":
            predicted_no_move += 1
            if case.expected_move_id == "no_move":
                correct_no_move += 1
        if case.expected_move_id == "no_move":
            expected_no_move += 1
        if record.result.reply.kind == "clarification":
            clarifications += 1
        if record.result.intent != "action_description":
            misrouted += 1

    return cast(
        dict[str, JsonValue],
        {
            "n": n,
            "accuracy": _round(rate(correct, n), 4),
            "confusion_matrix": confusion_matrix(pairs),
            "no_move_precision": _round(rate(correct_no_move, predicted_no_move), 4),
            "no_move_recall": _round(rate(correct_no_move, expected_no_move), 4),
            "clarification_rate": _round(rate(clarifications, n), 4),
            "misrouted": misrouted,
        },
    )


def _system_bucket(records: Sequence[CaseRecord]) -> dict[str, JsonValue]:
    latencies = [record.latency_ms for record in records]
    input_tokens: list[float] = []
    output_tokens: list[float] = []
    costs: list[float] = []
    unknown_calls = 0
    for record in records:
        case_input = 0
        case_output = 0
        case_cost = 0.0
        has_unknown = False
        for generation in record.turn_generations:
            case_input += generation.response.input_tokens
            case_output += generation.response.output_tokens
            if generation.response.cost_usd is None:
                has_unknown = True
                unknown_calls += 1
            else:
                case_cost += generation.response.cost_usd
        input_tokens.append(case_input)
        output_tokens.append(case_output)
        if not has_unknown:
            costs.append(case_cost)

    return cast(
        dict[str, JsonValue],
        {
            "n": len(records),
            "latency_ms_p50": _round(percentile(latencies, 50), 1),
            "latency_ms_p95": _round(percentile(latencies, 95), 1),
            "input_tokens_mean": _round(_mean(input_tokens), 1),
            "output_tokens_mean": _round(_mean(output_tokens), 1),
            "cost_usd_mean": _round(_mean(costs), 6),
            "cost_unknown_calls": unknown_calls,
        },
    )


def system_metrics(records: Sequence[CaseRecord]) -> dict[str, JsonValue]:
    buckets: dict[str, list[CaseRecord]] = {}
    for record in records:
        intent = record.result.intent or "error"
        buckets.setdefault(intent, []).append(record)

    result: dict[str, JsonValue] = {"all": _system_bucket(records)}
    for intent in _SYSTEM_INTENT_ORDER:
        if intent in buckets:
            result[intent] = _system_bucket(buckets[intent])
    return result
