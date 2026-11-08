"""Report building: the JSON shape (`schema_version` 1), its Markdown summary, and
file naming/writing (spec 009 D4/D12/D19, *Report JSON*).

`build_report` assembles one JSON-safe `dict` from a run's `Dataset`s, `EvalConfig`
and `RunOutcome`; nothing here calls a port or reads the clock, so the exact
`started_at`/`finished_at`/`git_commit` are the caller's job (`evals/run.py`, D19).
No secret ever reaches the report: only `EvalConfig`, dataset metadata and
`CaseRecord`s are read, none of which carry one (spec 009 *Authorization & Security*).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from backend.composition import REPO_ROOT
from evals.budget import generation_cost
from evals.config import EvalConfig
from evals.datasets import Dataset, DatasetName, MoveCase, RouterCase, RulesCase
from evals.metrics import (
    JsonValue,
    move_metrics,
    recall_at_k,
    router_metrics,
    rules_metrics,
    system_metrics,
)
from evals.runner import CaseRecord, RunOutcome

SCHEMA_VERSION: Literal[1] = 1

_MAX_MARKDOWN_FAILURES = 20


def _round(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def _dataset_file(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _turn_totals(record: CaseRecord) -> tuple[int, int, float | None]:
    input_tokens = 0
    output_tokens = 0
    cost: float | None = 0.0
    for generation in record.turn_generations:
        input_tokens += generation.response.input_tokens
        output_tokens += generation.response.output_tokens
        if cost is not None:
            if generation.response.cost_usd is None:
                cost = None
            else:
                cost += generation.response.cost_usd
    return input_tokens, output_tokens, cost


def _common_case_fields(record: CaseRecord) -> dict[str, object]:
    input_tokens, output_tokens, cost = _turn_totals(record)
    return {
        "id": record.case.id,
        "trace_id": record.trace_id,
        "intent": record.result.intent,
        "kind": record.result.reply.kind,
        "latency_ms": _round(record.latency_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": _round(cost, 6),
    }


def _citation_counts_for_case(record: CaseRecord) -> tuple[int, int]:
    generation = next(
        (g for g in record.turn_generations if g.node == "answer_with_citations"),
        None,
    )
    if generation is None:
        return 0, 0
    valid = (
        len(record.result.reply.citations)
        if record.result.reply.kind == "rules_answer"
        else 0
    )
    stripped_event = next(
        (e for e in record.events if e.name == "citations_stripped"), None
    )
    stripped = 0
    if stripped_event is not None:
        count = stripped_event.attributes.get("count", 0)
        if isinstance(count, int):
            stripped = count
    return valid, stripped


def _case_key_fact_coverage(record: CaseRecord, *, answerable: bool) -> float | None:
    if not answerable or record.judge_error is not None:
        return None
    if record.result.reply.kind != "rules_answer":
        return 0.0
    if not record.verdicts:
        return 0.0
    present = sum(1 for verdict in record.verdicts if verdict.present)
    return present / len(record.verdicts)


def _case_entry(dataset_name: DatasetName, record: CaseRecord) -> dict[str, object]:
    entry = _common_case_fields(record)

    if dataset_name == "router":
        router_case = record.case
        assert isinstance(router_case, RouterCase)
        predicted = record.result.intent or "error"
        entry["correct"] = predicted == router_case.expected_intent
        entry["expected_intent"] = router_case.expected_intent
        return entry

    if dataset_name == "move_classification":
        move_case = record.case
        assert isinstance(move_case, MoveCase)
        classification = record.result.classification
        predicted_move = (
            classification.move_id if classification is not None else "(not routed)"
        )
        entry["correct"] = (
            predicted_move == move_case.expected_move_id
            or predicted_move in move_case.acceptable_alternatives
        )
        entry["expected_move_id"] = move_case.expected_move_id
        entry["acceptable_alternatives"] = list(move_case.acceptable_alternatives)
        entry["predicted_move_id"] = predicted_move
        entry["confidence"] = (
            classification.confidence if classification is not None else None
        )
        entry["clarified"] = record.result.reply.kind == "clarification"
        return entry

    rules_case = record.case
    assert isinstance(rules_case, RulesCase)
    answerable = rules_case.answerable
    valid, stripped = _citation_counts_for_case(record)
    recall = (
        recall_at_k(
            rules_case.expected_section_ids, record.result.retrieved_section_ids
        )
        if answerable
        else None
    )
    facts = (
        [
            {
                "index": verdict.index,
                "fact": verdict.fact,
                "present": verdict.present,
                "evidence": verdict.evidence,
            }
            for verdict in record.verdicts
        ]
        if record.verdicts is not None
        else None
    )
    entry["expected_section_ids"] = list(rules_case.expected_section_ids)
    entry["retrieved_section_ids"] = list(record.result.retrieved_section_ids)
    entry["recall"] = _round(recall, 4)
    entry["citations_valid"] = valid
    entry["citations_stripped"] = stripped
    entry["refused"] = record.result.reply.kind == "rules_not_found"
    entry["key_fact_coverage"] = _round(
        _case_key_fact_coverage(record, answerable=answerable), 4
    )
    entry["facts"] = facts
    entry["judge_error"] = record.judge_error
    return entry


def _metrics_for(
    name: DatasetName, records: Sequence[CaseRecord], config: EvalConfig
) -> dict[str, JsonValue]:
    if name == "router":
        return router_metrics(records)
    if name == "rules_qa":
        return rules_metrics(records, config.graph.retrieval_k)
    return move_metrics(records)


def _eval_overhead(records: Sequence[CaseRecord]) -> dict[str, object]:
    judge_calls = 0
    judge_cost = 0.0
    for record in records:
        for generation in record.judge_generations:
            judge_calls += 1
            cost, _unknown = generation_cost(generation)
            judge_cost += cost
    return {"judge_calls": judge_calls, "judge_cost_usd": _round(judge_cost, 6)}


def _dataset_entry(
    dataset: Dataset, records: Sequence[CaseRecord], config: EvalConfig
) -> dict[str, object]:
    entry: dict[str, object] = {
        "file": _dataset_file(dataset.path),
        "sha256": dataset.sha256,
        "rows": len(dataset.cases),
        "completed": len(records),
        "metrics": _metrics_for(dataset.name, records, config),
        "system": system_metrics(records),
    }
    if dataset.name == "rules_qa":
        entry["eval_overhead"] = _eval_overhead(records)
    entry["cases"] = [_case_entry(dataset.name, record) for record in records]
    return entry


def build_report(
    *,
    run_id: str,
    status: Literal["completed", "aborted_budget"],
    started_at: datetime,
    finished_at: datetime,
    git_commit: str | None,
    config: EvalConfig,
    datasets: Sequence[Dataset],
    budget_usd: float,
    estimated_usd: float,
    outcome: RunOutcome,
) -> dict[str, JsonValue]:
    # Imported here, not at module scope: `evals.run` imports this module (the CLI
    # calls `build_report`/`write_report`/`report_paths`), so a top-level import
    # back would be circular. `TRACE_NAME` is canonically owned by `evals.run`
    # (spec 009 Constants); by the time this function runs, both modules are
    # already fully loaded.
    from evals.run import TRACE_NAME

    dataset_entries: dict[str, object] = {
        dataset.name: _dataset_entry(
            dataset, outcome.records.get(dataset.name, []), config
        )
        for dataset in datasets
    }

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "git_commit": git_commit,
        "config": {
            "name": config.name,
            "sha256": config.sha256,
            "models": {
                "router": config.models.router,
                "classifier": config.models.classifier,
                "answer": config.models.answer,
                "embeddings": config.models.embeddings,
                "judge": config.models.judge,
            },
            "graph": dataclasses.asdict(config.graph),
        },
        "budget": {
            "limit_usd": _round(budget_usd, 6),
            "estimated_usd": _round(estimated_usd, 6),
            "spent_usd": _round(outcome.spent_usd, 6),
            "unknown_cost_calls": outcome.unknown_cost_calls,
        },
        "langfuse": {"session_id": run_id, "trace_name": TRACE_NAME},
        "labels": {"all_rows_reviewed": True},
        "datasets": dataset_entries,
    }
    return cast(dict[str, JsonValue], report)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _case_failed(case: Mapping[str, JsonValue]) -> bool:
    if "correct" in case:
        return case["correct"] is False
    expected_sections = case.get("expected_section_ids")
    if isinstance(expected_sections, list):
        answerable = len(expected_sections) > 0
        kind = case.get("kind")
        if answerable:
            return kind != "rules_answer"
        return kind != "rules_not_found"
    return False


def render_markdown(report: Mapping[str, JsonValue]) -> str:
    config = cast("dict[str, JsonValue]", report["config"])
    budget = cast("dict[str, JsonValue]", report["budget"])
    datasets = cast("dict[str, JsonValue]", report["datasets"])

    lines: list[str] = [
        f"# Eval report: {config['name']}",
        "",
        f"- run_id: {report['run_id']}",
        f"- status: {report['status']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- git_commit: {_fmt(report['git_commit'])}",
        (
            f"- budget: limit ${_fmt(budget['limit_usd'])}, "
            f"estimated ${_fmt(budget['estimated_usd'])}, "
            f"spent ${_fmt(budget['spent_usd'])}, "
            f"unknown-cost calls {budget['unknown_cost_calls']}"
        ),
        "",
    ]

    for name, raw_entry in datasets.items():
        entry = cast("dict[str, JsonValue]", raw_entry)
        lines.append(f"## {name}")
        lines.append("")
        sha = cast(str, entry["sha256"])
        lines.append(f"- file: {entry['file']} (sha256 {sha[:12]})")
        lines.append(f"- rows: {entry['rows']}, completed: {entry['completed']}")
        lines.append("")

        lines.append("Metrics:")
        metrics = cast("dict[str, JsonValue]", entry["metrics"])
        for key, value in metrics.items():
            if key == "confusion_matrix":
                continue
            lines.append(f"- {key}: {_fmt(value)}")
        lines.append("")

        lines.append("System:")
        system = cast("dict[str, JsonValue]", entry["system"])
        for bucket_name, raw_bucket in system.items():
            bucket = cast("dict[str, JsonValue]", raw_bucket)
            lines.append(
                f"- {bucket_name}: n={bucket['n']}, "
                f"p50={_fmt(bucket['latency_ms_p50'])}ms, "
                f"p95={_fmt(bucket['latency_ms_p95'])}ms, "
                f"cost_mean=${_fmt(bucket['cost_usd_mean'])}"
            )
        lines.append("")

        if "eval_overhead" in entry:
            overhead = cast("dict[str, JsonValue]", entry["eval_overhead"])
            lines.append(
                f"Judge overhead: {overhead['judge_calls']} call(s), "
                f"${_fmt(overhead['judge_cost_usd'])}"
            )
            lines.append("")

        cases = cast("list[JsonValue]", entry["cases"])
        failures = [
            cast("dict[str, JsonValue]", case)
            for case in cases
            if _case_failed(cast("dict[str, JsonValue]", case))
        ]
        lines.append(f"Failures: {len(failures)}")
        shown = failures[:_MAX_MARKDOWN_FAILURES]
        for case in shown:
            lines.append(f"- {case['id']}: kind={case['kind']}")
        remaining = len(failures) - len(shown)
        if remaining > 0:
            lines.append(f"… and {remaining} more")
        lines.append("")

    return "\n".join(lines) + "\n"


def report_paths(reports_dir: Path, date: str, config_name: str) -> tuple[Path, Path]:
    base = f"{date}-{config_name}"
    json_path = reports_dir / f"{base}.json"
    md_path = reports_dir / f"{base}.md"
    if not json_path.exists() and not md_path.exists():
        return json_path, md_path

    suffix = 2
    while True:
        json_path = reports_dir / f"{base}-{suffix}.json"
        md_path = reports_dir / f"{base}-{suffix}.md"
        if not json_path.exists() and not md_path.exists():
            return json_path, md_path
        suffix += 1


def write_report(
    report: Mapping[str, JsonValue], json_path: Path, md_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
