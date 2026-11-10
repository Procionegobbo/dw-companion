"""Tests for `evals/compare.py` (spec 010): report loading, the comparability
gate, headline metric extraction, Markdown rendering and the CLI (`main`).
`report(...)` builds a spec 009-shaped report dict for `tmp_path` fixtures
only (D1, *Testing* fixture rule) - never under `evals/reports/` or
`evals/datasets/`."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

import pytest

from backend.adapters.openrouter import ModelPrice
from backend.tests.graph_helpers import chunk, classifier_json, router_json
from evals.compare import (
    TABLE_END,
    TABLE_START,
    ComparisonError,
    LoadedReport,
    Unit,
    assign_labels,
    case_flips,
    check_comparable,
    config_diff,
    format_delta,
    format_value,
    headline_rows,
    load_report,
    main,
    render_comparison,
)
from evals.run import main as run_main

from .helpers import (
    FAKE_ENV,
    fake_services,
    fixture_paths,
    move_row,
    router_row,
    rules_row,
    write_jsonl,
)

_NOW: Final = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)

_RATE: Final = 0.11
_USD: Final = 0.000111
_LATENCY: Final = 111.0

_END_TO_END_PRICE: Final = ModelPrice(
    prompt_usd_per_token=1e-6, completion_usd_per_token=2e-6
)

_DEFAULT_GRAPH: Final[dict[str, object]] = {
    "retrieval_k": 6,
    "closest_sections_limit": 3,
    "clarify_threshold": 0.6,
    "router_max_tokens": 100,
    "classifier_max_tokens": 400,
    "answer_max_tokens": 700,
    "explain_max_tokens": 300,
    "answer_temperature": 0.0,
}

_DEFAULT_MODELS: Final[dict[str, str]] = {
    "router": "m-router",
    "classifier": "m-classifier",
    "answer": "m-answer",
    "embeddings": "m-embeddings",
}

_ALL_DATASETS: Final = ("router", "rules_qa", "move_classification")


def _default_cases(name: str) -> list[dict[str, object]]:
    if name == "router":
        return [
            {
                "id": "router-001",
                "trace_id": "t",
                "intent": "rules_question",
                "kind": "rules_answer",
                "latency_ms": _LATENCY,
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": _USD,
                "correct": True,
                "expected_intent": "rules_question",
            }
        ]
    if name == "rules_qa":
        return [
            {
                "id": "rules-001",
                "trace_id": "t",
                "intent": "rules_question",
                "kind": "rules_answer",
                "latency_ms": _LATENCY,
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": _USD,
                "expected_section_ids": ["s"],
                "retrieved_section_ids": ["s"],
                "recall": _RATE,
                "citations_valid": 1,
                "citations_stripped": 0,
                "refused": False,
                "key_fact_coverage": _RATE,
                "facts": [],
                "judge_error": None,
            }
        ]
    return [
        {
            "id": "move-001",
            "trace_id": "t",
            "intent": "action_description",
            "kind": "move",
            "latency_ms": _LATENCY,
            "input_tokens": 1,
            "output_tokens": 1,
            "cost_usd": _USD,
            "correct": True,
            "expected_move_id": "hack-and-slash",
            "acceptable_alternatives": [],
            "predicted_move_id": "hack-and-slash",
            "confidence": 0.9,
            "clarified": False,
        }
    ]


def _default_metrics(name: str) -> dict[str, object]:
    if name == "router":
        return {"n": 1, "accuracy": _RATE, "confusion_matrix": {}}
    if name == "rules_qa":
        return {
            "n": 1,
            "answerable_n": 1,
            "unanswerable_n": 0,
            "retrieval_k": 6,
            "recall_at_k": _RATE,
            "citations_valid": 0,
            "citations_stripped": 0,
            "answers_without_citations": 0,
            "citation_validity_rate": _RATE,
            "key_fact_coverage": _RATE,
            "key_fact_judged_n": 1,
            "judge_errors": 0,
            "correct_refusal_rate": _RATE,
            "misrouted": 0,
        }
    return {
        "n": 1,
        "accuracy": _RATE,
        "confusion_matrix": {},
        "no_move_precision": _RATE,
        "no_move_recall": _RATE,
        "clarification_rate": _RATE,
        "misrouted": 0,
    }


def report(
    config: str = "a",
    *,
    judge: str = "m-judge",
    models: Mapping[str, str] | None = None,
    graph: Mapping[str, object] | None = None,
    datasets: Mapping[str, Mapping[str, object]] | None = None,
    git_commit: str | None = "c0ffee",
    run_id: str = "0123456789abcdef0123456789abcdef",
) -> dict[str, object]:
    """Build a spec 009-shaped report dict for `compare.py` tests.

    Synthetic test data; these values are not eval results and must never be
    copied into docs or reports. Every default rate metric is 0.11, every
    default USD value 0.000111 and every default latency 111.0 - a test
    overrides only the specific values it asserts on.
    """
    model_values = dict(_DEFAULT_MODELS)
    model_values["judge"] = judge
    if models:
        model_values.update(models)

    graph_values = dict(_DEFAULT_GRAPH)
    if graph:
        graph_values.update(graph)

    default_datasets: dict[str, Mapping[str, object]] = {
        name: {} for name in _ALL_DATASETS
    }
    dataset_overrides: Mapping[str, Mapping[str, object]] = (
        datasets if datasets is not None else default_datasets
    )
    dataset_entries: dict[str, object] = {}
    for name, override in dataset_overrides.items():
        cases = cast("list[object]", override.get("cases", _default_cases(name)))
        metrics = dict(_default_metrics(name))
        metrics.update(cast("Mapping[str, object]", override.get("metrics", {})))
        dataset_entries[name] = {
            "file": f"evals/datasets/{name}.jsonl",
            "sha256": override.get("sha256", f"sha-{name}".ljust(64, "0")),
            "rows": override.get("rows", len(cases)),
            "completed": override.get("completed", len(cases)),
            "metrics": metrics,
            "cases": cases,
        }

    return {
        "schema_version": 1,
        "run_id": run_id,
        "status": "completed",
        "started_at": "2026-11-09T00:00:00+00:00",
        "finished_at": "2026-11-09T00:10:00+00:00",
        "git_commit": git_commit,
        "config": {
            "name": config,
            "sha256": f"sha-{config}".ljust(64, "0"),
            "models": model_values,
            "graph": graph_values,
        },
        "budget": {
            "limit_usd": 3.0,
            "estimated_usd": 1.0,
            "spent_usd": 0.5,
            "unknown_cost_calls": 0,
        },
        "langfuse": {"session_id": run_id, "trace_name": "eval_turn"},
        "labels": {"all_rows_reviewed": True},
        "datasets": dataset_entries,
    }


def _loaded(
    tmp_path: Path, reports: Sequence[Mapping[str, object]]
) -> tuple[LoadedReport, ...]:
    paths: list[Path] = []
    for i, data in enumerate(reports):
        path = tmp_path / f"r{i}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        paths.append(path)
    parsed = [load_report(path) for path in paths]
    return assign_labels(paths, parsed)


def _mutate_schema_version(data: dict[str, object]) -> None:
    data["schema_version"] = 2


def _mutate_status(data: dict[str, object]) -> None:
    data["status"] = "aborted_budget"


def _mutate_unreviewed(data: dict[str, object]) -> None:
    cast("dict[str, object]", data["labels"])["all_rows_reviewed"] = False


def _mutate_missing_datasets(data: dict[str, object]) -> None:
    del data["datasets"]


def _mutate_latency_string(data: dict[str, object]) -> None:
    datasets = cast("dict[str, object]", data["datasets"])
    router = cast("dict[str, object]", datasets["router"])
    cases = cast("list[dict[str, object]]", router["cases"])
    cases[0]["latency_ms"] = "not-a-number"


@pytest.mark.parametrize(
    ("kind", "mutator", "expected_prefix"),
    [
        pytest.param("missing", None, "no such report file", id="missing_file"),
        pytest.param("invalid_json", None, "not valid JSON", id="invalid_json"),
        pytest.param(
            "mutate",
            _mutate_schema_version,
            "unsupported report schema_version 2",
            id="schema_version_2",
        ),
        pytest.param(
            "mutate",
            _mutate_status,
            "report status is aborted_budget",
            id="status_aborted_budget",
        ),
        pytest.param(
            "mutate",
            _mutate_unreviewed,
            "report is not based on fully reviewed datasets",
            id="not_all_rows_reviewed",
        ),
        pytest.param(
            "mutate",
            _mutate_missing_datasets,
            "not a spec 009 report (",
            id="missing_datasets",
        ),
        pytest.param(
            "mutate",
            _mutate_latency_string,
            "not a spec 009 report (",
            id="latency_ms_a_string",
        ),
    ],
)
def test_load_report_errors(
    tmp_path: Path,
    kind: str,
    mutator: Callable[[dict[str, object]], None] | None,
    expected_prefix: str,
) -> None:
    path = tmp_path / "report.json"
    if kind == "missing":
        pass
    elif kind == "invalid_json":
        path.write_text("not valid json {{", encoding="utf-8")
    else:
        assert mutator is not None
        data = report()
        mutator(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ComparisonError) as excinfo:
        load_report(path)
    assert str(excinfo.value).startswith(f"{path}: {expected_prefix}")


def test_load_report_accepts_null_intent_case(tmp_path: Path) -> None:
    """`intent` is nullable (`TurnResult.intent` is `None` on an error-kind
    turn, per `evals/report.py`); a case with `intent: None` must pass
    structure validation like the already-nullable `cost_usd` field, not
    raise `ComparisonError`."""
    router_base = _default_cases("router")[0]
    data = report(
        datasets={
            "router": {
                "cases": [{**router_base, "intent": None, "kind": "error"}],
            }
        }
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_report(path)

    datasets = cast("Mapping[str, object]", loaded["datasets"])
    router = cast("Mapping[str, object]", datasets["router"])
    cases = cast("list[dict[str, object]]", router["cases"])
    assert cases[0]["intent"] is None


def test_rejects_different_judge(tmp_path: Path) -> None:
    reference = report(config="a", judge="m-judge-a")
    candidate = report(config="b", judge="m-judge-b")
    loaded = _loaded(tmp_path, [reference, candidate])

    with pytest.raises(ComparisonError) as excinfo:
        check_comparable(loaded)

    message = str(excinfo.value)
    assert "different judge models" in message
    assert "key-fact coverage is not comparable" in message


def test_rejects_dataset_sha_mismatch(tmp_path: Path) -> None:
    reference = report(config="a", datasets={"rules_qa": {"sha256": "a" * 64}})
    candidate = report(config="b", datasets={"rules_qa": {"sha256": "b" * 64}})
    loaded = _loaded(tmp_path, [reference, candidate])

    with pytest.raises(ComparisonError) as excinfo:
        check_comparable(loaded)

    message = str(excinfo.value)
    assert "rules_qa" in message
    assert "a" * 12 in message
    assert "b" * 12 in message


def test_rejects_no_shared_dataset(tmp_path: Path) -> None:
    reference = report(config="a", datasets={"router": {}})
    candidate = report(config="b", datasets={"rules_qa": {}})
    loaded = _loaded(tmp_path, [reference, candidate])

    with pytest.raises(ComparisonError, match="no dataset is present in every report"):
        check_comparable(loaded)


def test_headline_rows_values_and_cases(tmp_path: Path) -> None:
    move_base = _default_cases("move_classification")[0]
    reference = report(
        config="a",
        datasets={
            "router": {"metrics": {"n": 10, "accuracy": 0.5}},
            "rules_qa": {
                "metrics": {
                    "n": 20,
                    "answerable_n": 15,
                    "unanswerable_n": 5,
                    "recall_at_k": 0.25,
                    "citation_validity_rate": 0.99,
                    "key_fact_coverage": 0.75,
                    "correct_refusal_rate": 0.4,
                }
            },
            "move_classification": {
                "metrics": {
                    "n": 8,
                    "accuracy": 0.6,
                    "no_move_precision": 0.3,
                    "no_move_recall": 0.2,
                    "clarification_rate": 0.1,
                },
                "cases": [
                    {**move_base, "id": "move-001", "expected_move_id": "no_move"},
                    {
                        **move_base,
                        "id": "move-002",
                        "expected_move_id": "hack-and-slash",
                    },
                    {**move_base, "id": "move-003", "expected_move_id": "no_move"},
                ],
            },
        },
    )
    candidate = report(config="b")
    loaded = _loaded(tmp_path, [reference, candidate])
    shared, _skipped = check_comparable(loaded)

    rows = {row.label: row for row in headline_rows(loaded, shared)}

    assert rows["Router accuracy"].cases == 10
    assert rows["Router accuracy"].values[0] == 0.5
    assert rows["Retrieval recall@6"].cases == 15
    assert rows["Retrieval recall@6"].values[0] == 0.25
    assert rows["Citation validity"].cases == 20
    assert rows["Citation validity"].values[0] == 0.99
    assert rows["Key-fact coverage"].cases == 15
    assert rows["Key-fact coverage"].values[0] == 0.75
    assert rows["Correct refusals"].cases == 5
    assert rows["Correct refusals"].values[0] == 0.4
    assert rows["Move accuracy"].cases == 8
    assert rows["Move accuracy"].values[0] == 0.6
    assert rows["no_move precision"].cases is None
    assert rows["no_move precision"].values[0] == 0.3
    assert rows["no_move recall"].cases == 2
    assert rows["no_move recall"].values[0] == 0.2
    assert rows["Clarification rate"].cases == 8
    assert rows["Clarification rate"].values[0] == 0.1


def test_cost_and_latency_recomputed_from_cases(tmp_path: Path) -> None:
    router_base = _default_cases("router")[0]
    move_base = _default_cases("move_classification")[0]
    reference = report(
        config="a",
        datasets={
            "router": {
                "cases": [
                    {
                        **router_base,
                        "id": "router-001",
                        "cost_usd": 0.01,
                        "latency_ms": 100.0,
                        "intent": "rules_question",
                    },
                    {
                        **router_base,
                        "id": "router-002",
                        "cost_usd": None,
                        "latency_ms": 200.0,
                        "intent": "rules_question",
                    },
                ]
            },
            "move_classification": {
                "cases": [
                    {
                        **move_base,
                        "id": "move-001",
                        "cost_usd": 0.02,
                        "latency_ms": 300.0,
                        "intent": "action_description",
                    },
                ]
            },
        },
    )
    candidate = report(
        config="b",
        datasets={
            "router": {
                "cases": [
                    {
                        **router_base,
                        "id": "router-001",
                        "cost_usd": None,
                        "latency_ms": 100.0,
                        "intent": "rules_question",
                    },
                    {
                        **router_base,
                        "id": "router-002",
                        "cost_usd": None,
                        "latency_ms": 200.0,
                        "intent": "rules_question",
                    },
                ]
            },
            "move_classification": {
                "cases": [
                    {
                        **move_base,
                        "id": "move-001",
                        "cost_usd": None,
                        "latency_ms": 300.0,
                        "intent": "action_description",
                    },
                ]
            },
        },
    )
    loaded = _loaded(tmp_path, [reference, candidate])
    shared, _skipped = check_comparable(loaded)
    rows = {row.label: row for row in headline_rows(loaded, shared)}

    # Cost per query: non-null cost_usd cases only, over all shared datasets.
    assert rows["Cost per query"].values[0] == pytest.approx((0.01 + 0.02) / 2)
    assert rows["Cost per query"].cases == 3
    # All cost_usd null for the candidate -> None ("n/a" when rendered).
    assert rows["Cost per query"].values[1] is None

    # Cost per rules question: restricted to intent == "rules_question".
    assert rows["Cost per rules question"].values[0] == pytest.approx(0.01)
    assert rows["Cost per rules question"].cases == 2

    # Cost per action description: restricted to intent == "action_description".
    assert rows["Cost per action description"].values[0] == pytest.approx(0.02)
    assert rows["Cost per action description"].cases == 1

    # Latency p50/p95 over all shared cases' latency_ms (100, 200, 300).
    assert rows["Latency p50"].values[0] == pytest.approx(200.0)
    assert rows["Latency p95"].values[0] == pytest.approx(290.0)
    assert rows["Latency p50"].cases == 3


@pytest.mark.parametrize(
    ("unit", "value", "reference", "expected_value", "expected_delta"),
    [
        pytest.param("rate", 0.875, 0.85, "87.5%", "+2.5 pp", id="rate"),
        pytest.param(
            "usd", 0.00125, 0.00085, "$0.00125", "+$0.00040 (+47%)", id="usd_positive"
        ),
        pytest.param(
            "usd", 0.00085, 0.00125, "$0.00085", "-$0.00040 (-32%)", id="usd_negative"
        ),
        pytest.param("usd", 0.00125, 0.0, "$0.00125", "+$0.00125", id="usd_ref_zero"),
        pytest.param("ms", 1840.0, 1960.0, "1840 ms", "-120 ms", id="ms"),
    ],
)
def test_format_value_and_delta(
    unit: Unit,
    value: float,
    reference: float,
    expected_value: str,
    expected_delta: str,
) -> None:
    assert format_value(unit, value) == expected_value
    assert format_delta(unit, reference, value) == expected_delta


def test_format_value_and_delta_none_renders_na() -> None:
    assert format_value("rate", None) == "n/a"
    assert format_delta("rate", None, 0.5) == "n/a"
    assert format_delta("rate", 0.5, None) == "n/a"


def test_recall_label_uses_k_or_flags_difference(tmp_path: Path) -> None:
    reference = report(config="a", datasets={"rules_qa": {}})
    same_k = report(config="b", datasets={"rules_qa": {}})
    loaded = _loaded(tmp_path, [reference, same_k])
    shared, _skipped = check_comparable(loaded)
    labels = [row.label for row in headline_rows(loaded, shared)]
    assert "Retrieval recall@6" in labels

    different_k = report(
        config="c", graph={"retrieval_k": 8}, datasets={"rules_qa": {}}
    )
    loaded2 = _loaded(tmp_path, [reference, different_k])
    shared2, _skipped2 = check_comparable(loaded2)
    labels2 = [row.label for row in headline_rows(loaded2, shared2)]
    assert "Retrieval recall@k (k differs, see Configurations)" in labels2


def test_shared_and_skipped_datasets_in_order(tmp_path: Path) -> None:
    full = report(config="a")
    partial = report(config="b", datasets={"router": {}, "move_classification": {}})
    loaded = _loaded(tmp_path, [full, partial])

    shared, skipped = check_comparable(loaded)
    assert shared == ("router", "move_classification")
    assert skipped == ("rules_qa",)

    rendered = render_comparison(loaded, shared, skipped, _NOW)
    assert "Skipped (not in every report): rules_qa." in rendered
    assert "Retrieval recall" not in rendered
    assert "Citation validity" not in rendered
    assert "Key-fact coverage" not in rendered
    assert "Correct refusals" not in rendered


def test_case_flips_router_and_move(tmp_path: Path) -> None:
    router_base = _default_cases("router")[0]
    router_cases_ref = [
        {**router_base, "id": f"router-{i:03d}", "correct": True} for i in range(1, 22)
    ]
    router_cases_cand = [
        {**router_base, "id": f"router-{i:03d}", "correct": False} for i in range(1, 22)
    ]
    move_base = _default_cases("move_classification")[0]
    move_cases_ref = [
        {**move_base, "id": "move-001", "correct": True},
        {**move_base, "id": "move-002", "correct": False},
        {**move_base, "id": "move-003", "correct": True},
        {**move_base, "id": "move-999", "correct": True},  # missing from candidate
    ]
    move_cases_cand = [
        {**move_base, "id": "move-001", "correct": False},
        {**move_base, "id": "move-002", "correct": True},
        {**move_base, "id": "move-003", "correct": True},
    ]
    reference = report(
        config="a",
        datasets={
            "router": {"cases": router_cases_ref},
            "move_classification": {"cases": move_cases_ref},
        },
    )
    candidate = report(
        config="b",
        datasets={
            "router": {"cases": router_cases_cand},
            "move_classification": {"cases": move_cases_cand},
        },
    )
    loaded = _loaded(tmp_path, [reference, candidate])
    ref, cand = loaded

    router_flips = case_flips(ref, cand, "router")
    assert router_flips.reference_only == tuple(f"router-{i:03d}" for i in range(1, 22))
    assert router_flips.candidate_only == ()

    move_flips = case_flips(ref, cand, "move_classification")
    # move-999 is missing from the candidate and must be ignored.
    assert move_flips.reference_only == ("move-001",)
    assert move_flips.candidate_only == ("move-002",)

    rendered = render_comparison(loaded, ("router", "move_classification"), (), _NOW)
    shown = ", ".join(f"router-{i:03d}" for i in range(1, 21))
    assert f"Correct only in {ref.label} (21): {shown}, … and 1 more" in rendered
    assert f"Correct only in {cand.label} (0): none" in rendered
    assert f"Correct only in {ref.label} (1): move-001" in rendered
    assert f"Correct only in {cand.label} (1): move-002" in rendered


def test_config_diff_lists_only_differing_settings(tmp_path: Path) -> None:
    baseline = report(config="baseline", models={"classifier": "openai/gpt-4.1-nano"})
    candidate = report(
        config="classifier-mini", models={"classifier": "openai/gpt-4.1-mini"}
    )
    loaded = _loaded(tmp_path, [baseline, candidate])

    diff = config_diff(loaded)
    assert diff == (
        ("models.classifier", ("openai/gpt-4.1-nano", "openai/gpt-4.1-mini")),
    )

    shared, skipped = check_comparable(loaded)
    rendered = render_comparison(loaded, shared, skipped, _NOW)
    assert "| `models.classifier` |" in rendered
    assert "Judge (identical in all reports): `m-judge`." in rendered

    identical_a = report(config="c")
    identical_b = report(config="c", run_id="1" * 32)
    loaded2 = _loaded(tmp_path, [identical_a, identical_b])
    assert config_diff(loaded2) == ()

    shared2, skipped2 = check_comparable(loaded2)
    rendered2 = render_comparison(loaded2, shared2, skipped2, _NOW)
    assert (
        "No setting differs: these are repeated runs of the same configuration."
        in rendered2
    )
    assert "Judge (identical in all reports): `m-judge`." in rendered2


def test_three_reports_have_delta_column_per_candidate(tmp_path: Path) -> None:
    loaded = _loaded(
        tmp_path, [report(config="a"), report(config="b"), report(config="c")]
    )
    shared, skipped = check_comparable(loaded)
    rendered = render_comparison(loaded, shared, skipped, _NOW)
    assert "| Metric | Cases | a | b | Δ b | c | Δ c |" in rendered


def test_table_markers_appear_once_and_wrap_table(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path, [report(config="a"), report(config="b")])
    shared, skipped = check_comparable(loaded)
    rendered = render_comparison(loaded, shared, skipped, _NOW)

    assert rendered.count(TABLE_START) == 1
    assert rendered.count(TABLE_END) == 1

    lines = rendered.split("\n")
    start_idx = lines.index(TABLE_START)
    end_idx = lines.index(TABLE_END)
    between = lines[start_idx + 1 : end_idx]
    assert len(between) >= 2
    for line in between:
        assert line.startswith("|")


def test_different_commits_note(tmp_path: Path) -> None:
    a = report(config="a", git_commit="aaaaaaaaaaaa1111")
    b = report(config="b", git_commit="bbbbbbbbbbbb2222")
    loaded = _loaded(tmp_path, [a, b])
    shared, skipped = check_comparable(loaded)
    rendered = render_comparison(loaded, shared, skipped, _NOW)
    assert "**Note:** reports come from different commits" in rendered

    c = report(config="c", git_commit=None)
    d = report(config="d", git_commit="cccccccccccc3333")
    loaded2 = _loaded(tmp_path, [c, d])
    shared2, skipped2 = check_comparable(loaded2)
    rendered2 = render_comparison(loaded2, shared2, skipped2, _NOW)
    assert "**Note:** reports come from different commits" in rendered2

    e = report(config="e", git_commit="dddddddddddd4444")
    f = report(config="f", git_commit="dddddddddddd4444")
    loaded3 = _loaded(tmp_path, [e, f])
    shared3, skipped3 = check_comparable(loaded3)
    rendered3 = render_comparison(loaded3, shared3, skipped3, _NOW)
    assert "**Note:** reports come from different commits" not in rendered3


def test_judge_errors_note(tmp_path: Path) -> None:
    a = report(config="a", datasets={"rules_qa": {"metrics": {"judge_errors": 2}}})
    b = report(config="b")
    loaded = _loaded(tmp_path, [a, b])
    shared, skipped = check_comparable(loaded)
    rendered = render_comparison(loaded, shared, skipped, _NOW)
    assert "Judge errors (excluded from key-fact coverage): a: 2." in rendered


def test_duplicate_config_names_get_run_id_suffix(tmp_path: Path) -> None:
    a = report(config="same", run_id="aaaaaa11111111111111111111111111")
    b = report(config="same", run_id="bbbbbb22222222222222222222222222")
    loaded = _loaded(tmp_path, [a, b])

    assert loaded[0].label == "same-aaaaaa"
    assert loaded[1].label == "same-bbbbbb"

    comparisons_dir = tmp_path / "comparisons"
    code = main(
        [str(loaded[0].path), str(loaded[1].path)],
        comparisons_dir=comparisons_dir,
        now=lambda: _NOW,
    )

    assert code == 0
    written = comparisons_dir / "2026-11-10-same-aaaaaa-vs-same-bbbbbb.md"
    assert written.exists()


@pytest.mark.parametrize("n", [1, 5])
def test_cli_report_count_bounds(
    tmp_path: Path, n: int, capsys: pytest.CaptureFixture[str]
) -> None:
    paths: list[Path] = []
    for i in range(n):
        path = tmp_path / f"r{i}.json"
        path.write_text(json.dumps(report(config=f"c{i}")), encoding="utf-8")
        paths.append(path)

    comparisons_dir = tmp_path / "comparisons"
    code = main(
        [str(p) for p in paths], comparisons_dir=comparisons_dir, now=lambda: _NOW
    )

    assert code == 2
    assert not comparisons_dir.exists()
    err = capsys.readouterr().err
    assert err.startswith("compare: error: ")
    assert f"got {n}" in err


def _expected_display(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return str(path)


def test_cli_writes_comparison_and_suffixes_on_collision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths: list[Path] = []
    for config in ("a", "b"):
        path = tmp_path / f"{config}.json"
        path.write_text(json.dumps(report(config=config)), encoding="utf-8")
        paths.append(path)

    comparisons_dir = tmp_path / "comparisons"

    code1 = main(
        [str(p) for p in paths], comparisons_dir=comparisons_dir, now=lambda: _NOW
    )
    out1 = capsys.readouterr().out.strip()
    first = comparisons_dir / "2026-11-10-a-vs-b.md"
    assert code1 == 0
    assert first.exists()
    assert out1 == f"compare: wrote {_expected_display(first)}"

    code2 = main(
        [str(p) for p in paths], comparisons_dir=comparisons_dir, now=lambda: _NOW
    )
    out2 = capsys.readouterr().out.strip()
    second = comparisons_dir / "2026-11-10-a-vs-b-2.md"
    assert code2 == 0
    assert second.exists()
    assert out2 == f"compare: wrote {_expected_display(second)}"


def test_cli_error_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths: list[Path] = []
    for config, judge in (("a", "m-judge-a"), ("b", "m-judge-b")):
        path = tmp_path / f"{config}.json"
        path.write_text(
            json.dumps(report(config=config, judge=judge)), encoding="utf-8"
        )
        paths.append(path)

    comparisons_dir = tmp_path / "comparisons"
    code = main(
        [str(p) for p in paths], comparisons_dir=comparisons_dir, now=lambda: _NOW
    )

    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("compare: error: ")
    assert not comparisons_dir.exists()


def test_compare_end_to_end_on_runner_reports(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "what is this?", "out_of_scope")],
    )
    write_jsonl(
        paths.datasets_dir / "rules_qa.jsonl",
        [
            rules_row(
                "rules-001",
                "what happens on a miss?",
                ["moves/hack-and-slash"],
                ["Fact one"],
            )
        ],
    )
    write_jsonl(
        paths.datasets_dir / "move_classification.jsonl",
        [move_row("move-001", "I attack the goblin", "hack-and-slash")],
    )
    (paths.configs_dir / "test-b.toml").write_text(
        "[models]\n"
        'router = "m-router"\n'
        'classifier = "m-classifier-b"\n'
        'answer = "m-answer"\n'
        'embeddings = "m-embeddings"\n'
        'judge = "m-judge"\n',
        encoding="utf-8",
    )

    def run_config(config_name: str) -> Path:
        factory, _tracer = fake_services(
            {
                "router": [
                    router_json("out_of_scope"),
                    router_json("rules_question"),
                    router_json("action_description"),
                ],
                "classifier": [classifier_json("hack-and-slash", confidence=0.9)],
                "answer": [
                    "Hack and Slash lets you deal damage. [[moves/hack-and-slash]]",
                    "You attack with your blade, triggering Hack and Slash.",
                ],
            },
            ['{"facts": [{"index": 0, "present": true, "evidence": "deal damage"}]}'],
            chunks=[chunk("moves/hack-and-slash", title="Hack and Slash")],
            prices={
                "m-router": _END_TO_END_PRICE,
                "m-classifier": _END_TO_END_PRICE,
                "m-classifier-b": _END_TO_END_PRICE,
                "m-answer": _END_TO_END_PRICE,
                "m-judge": _END_TO_END_PRICE,
            },
        )
        code = run_main(
            ["--config", config_name],
            environ=FAKE_ENV,
            paths=paths,
            services_factory=factory,
        )
        assert code == 0
        matches = sorted(paths.reports_dir.glob(f"*-{config_name}.json"))
        assert len(matches) == 1
        return matches[0]

    reference_report = run_config("test")
    candidate_report = run_config("test-b")

    comparisons_dir = tmp_path / "comparisons"
    code = main(
        [str(reference_report), str(candidate_report)],
        comparisons_dir=comparisons_dir,
        now=lambda: _NOW,
    )
    assert code == 0

    files = list(comparisons_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")

    for label in (
        "Router accuracy",
        "Retrieval recall@",
        "Citation validity",
        "Key-fact coverage",
        "Correct refusals",
        "Move accuracy",
        "no_move precision",
        "no_move recall",
        "Clarification rate",
        "Cost per query",
        "Cost per rules question",
        "Cost per action description",
        "Latency p50",
        "Latency p95",
    ):
        assert label in content

    assert "| `models.classifier` |" in content
    assert "### router:" in content
    assert "### move_classification:" in content
