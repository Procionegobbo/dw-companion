"""Tests for `evals/report.py`: report shape, key order, Markdown rendering,
file-name collision suffixing and rounding (spec 009 *Report JSON*)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from backend.graph.deps import GraphSettings
from backend.graph.state import Reply, TurnResult
from backend.ports.llm import LLMRequest, LLMResponse
from backend.ports.tracer import GenerationTrace
from evals.config import EvalConfig, EvalModels
from evals.datasets import Dataset, RouterCase, RulesCase
from evals.metrics import JsonValue
from evals.report import build_report, render_markdown, report_paths
from evals.runner import CaseRecord, RunOutcome

_MODELS = EvalModels(
    router="m-router",
    classifier="m-classifier",
    answer="m-answer",
    embeddings="m-embeddings",
    judge="m-judge",
)
_REQUEST = LLMRequest(
    role="answer", system="s", user="u", max_tokens=10, temperature=0.0
)


def _config() -> EvalConfig:
    return EvalConfig(
        name="test",
        sha256="cfgsha",
        models=_MODELS,
        graph=GraphSettings(retrieval_k=6),
    )


def _generation(
    cost_usd: float | None, *, node: str = "answer_with_citations"
) -> GenerationTrace:
    response = LLMResponse(
        text="t",
        model="m-answer",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost_usd,
    )
    return GenerationTrace(
        trace_id="t",
        session_id="r",
        node=node,
        request=_REQUEST,
        response=response,
        latency_ms=1.0,
    )


def _router_case_record(
    case_id: str, *, correct: bool, latency_ms: float = 100.0
) -> CaseRecord:
    case = RouterCase(
        id=case_id, message="m", expected_intent="rules_question", reviewed=True
    )
    result = TurnResult(
        reply=Reply(kind="clarification", text="x"),
        intent="rules_question" if correct else "out_of_scope",
        router_confidence=0.9,
        classification=None,
        retrieved_section_ids=(),
    )
    return CaseRecord(
        dataset="router",
        case=case,
        trace_id=f"trace-{case_id}",
        result=result,
        latency_ms=latency_ms,
        turn_generations=(_generation(0.0000012345, node="router"),),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(),
    )


def _rules_case_record() -> CaseRecord:
    case = RulesCase(
        id="rules-001",
        message="m",
        expected_section_ids=("moves/last-breath",),
        key_facts=("fact",),
        reviewed=True,
    )
    result = TurnResult(
        reply=Reply(kind="rules_answer", text="t"),
        intent="rules_question",
        router_confidence=0.9,
        classification=None,
        retrieved_section_ids=("moves/last-breath",),
    )
    return CaseRecord(
        dataset="rules_qa",
        case=case,
        trace_id="trace-rules-001",
        result=result,
        latency_ms=50.0,
        turn_generations=(_generation(0.002),),
        events=(),
        verdicts=None,
        judge_error=None,
        judge_generations=(_generation(0.0000005, node="judge_key_facts"),),
    )


def _datasets() -> list[Dataset]:
    router = Dataset(
        name="router",
        path=Path("evals/datasets/router.jsonl"),
        sha256="routersha",
        cases=(
            RouterCase(
                id="router-001",
                message="m",
                expected_intent="rules_question",
                reviewed=True,
            ),
            RouterCase(
                id="router-002",
                message="m",
                expected_intent="rules_question",
                reviewed=True,
            ),
        ),
    )
    rules_qa = Dataset(
        name="rules_qa",
        path=Path("evals/datasets/rules_qa.jsonl"),
        sha256="rulessha",
        cases=(
            RulesCase(
                id="rules-001",
                message="m",
                expected_section_ids=("moves/last-breath",),
                key_facts=("fact",),
                reviewed=True,
            ),
        ),
    )
    return [router, rules_qa]


def _build_sample_report(
    *, router_records: list[CaseRecord] | None = None
) -> dict[str, JsonValue]:
    records = (
        router_records
        if router_records is not None
        else [
            _router_case_record("router-001", correct=True),
            _router_case_record("router-002", correct=False),
        ]
    )
    outcome = RunOutcome(
        records={"router": records, "rules_qa": [_rules_case_record()]},
        aborted=False,
        spent_usd=0.123456789,
        unknown_cost_calls=0,
    )
    return build_report(
        run_id="run-123",
        status="completed",
        started_at=datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 11, 20, 12, 5, 0, tzinfo=UTC),
        git_commit="abc123",
        config=_config(),
        datasets=_datasets(),
        budget_usd=3.0,
        estimated_usd=1.0500005,
        outcome=outcome,
    )


def test_report_shape_and_key_order() -> None:
    report = _build_sample_report()

    assert list(report.keys()) == [
        "schema_version",
        "run_id",
        "status",
        "started_at",
        "finished_at",
        "git_commit",
        "config",
        "budget",
        "langfuse",
        "labels",
        "datasets",
    ]
    assert report["schema_version"] == 1
    assert report["labels"] == {"all_rows_reviewed": True}

    config = cast("dict[str, object]", report["config"])
    assert config["sha256"] == "cfgsha"

    datasets = cast("dict[str, object]", report["datasets"])
    router_entry = cast("dict[str, object]", datasets["router"])
    assert router_entry["sha256"] == "routersha"
    assert list(router_entry.keys()) == [
        "file",
        "sha256",
        "rows",
        "completed",
        "metrics",
        "system",
        "cases",
    ]

    rules_entry = cast("dict[str, object]", datasets["rules_qa"])
    assert rules_entry["sha256"] == "rulessha"
    assert list(rules_entry.keys()) == [
        "file",
        "sha256",
        "rows",
        "completed",
        "metrics",
        "system",
        "eval_overhead",
        "cases",
    ]


def test_report_paths_suffix_on_collision(tmp_path: Path) -> None:
    (tmp_path / "2026-11-20-test.json").write_text("{}", encoding="utf-8")

    json_path, md_path = report_paths(tmp_path, "2026-11-20", "test")

    assert json_path == tmp_path / "2026-11-20-test-2.json"
    assert md_path == tmp_path / "2026-11-20-test-2.md"


def test_report_paths_no_collision(tmp_path: Path) -> None:
    json_path, md_path = report_paths(tmp_path, "2026-11-20", "baseline")

    assert json_path == tmp_path / "2026-11-20-baseline.json"
    assert md_path == tmp_path / "2026-11-20-baseline.md"


def test_markdown_contains_metrics_and_failures() -> None:
    router_records = [
        _router_case_record(f"router-{i:03d}", correct=False) for i in range(25)
    ]
    report = _build_sample_report(router_records=router_records)

    markdown = render_markdown(report)

    assert "## router" in markdown
    assert "## rules_qa" in markdown
    assert "n/a" in markdown  # a null metric (e.g. correct_refusal_rate)
    assert "Failures: 25" in markdown
    assert "… and 5 more" in markdown


def test_rounding() -> None:
    report = _build_sample_report()

    budget = cast("dict[str, object]", report["budget"])
    assert budget["spent_usd"] == round(0.123456789, 6)
    assert budget["estimated_usd"] == round(1.0500005, 6)

    datasets = cast("dict[str, object]", report["datasets"])
    router_entry = cast("dict[str, object]", datasets["router"])
    system = cast("dict[str, object]", router_entry["system"])
    all_bucket = cast("dict[str, object]", system["all"])
    assert all_bucket["latency_ms_p50"] == 100.0
    assert isinstance(all_bucket["cost_usd_mean"], float)
    assert all_bucket["cost_usd_mean"] == round(0.0000012345, 6)

    metrics = cast("dict[str, object]", router_entry["metrics"])
    assert metrics["accuracy"] == round(1 / 2, 4)

    rules_entry = cast("dict[str, object]", datasets["rules_qa"])
    overhead = cast("dict[str, object]", rules_entry["eval_overhead"])
    assert overhead["judge_cost_usd"] == round(0.0000005, 6)
