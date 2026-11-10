"""Report loading, comparability checks, metric extraction, Markdown rendering
and the CLI for the model-tuning round (spec 010, *Data Model*).

`compare.py` is a pure, offline consumer of spec 009 report files: it never
touches the runtime, datasets or network, and imports only the stdlib plus
spec 009's `evals.datasets` (`DATASET_ORDER`, `DatasetName`) and `evals.metrics`
(`percentile`, `JsonValue`) (D18). It covers validation (`load_report`),
labelling (`assign_labels`), the comparability gate (`check_comparable`),
headline metric extraction (`headline_rows`, `format_value`, `format_delta`),
per-case flips (`case_flips`), configuration diffs (`config_diff`), Markdown
rendering (`render_comparison`) and the `main` CLI entry point (spec 010
story 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Final, Literal, cast

from evals.datasets import DATASET_ORDER, DatasetName
from evals.metrics import JsonValue, percentile

MIN_REPORTS: Final = 2
MAX_REPORTS: Final = 4
REPO_ROOT: Final = Path(__file__).resolve().parent.parent
DEFAULT_COMPARISONS_DIR: Final = REPO_ROOT / "evals/reports/comparisons"

MAX_FLIP_IDS: Final = 20
TABLE_START: Final = "<!-- comparison-table:start -->"
TABLE_END: Final = "<!-- comparison-table:end -->"

_SCHEMA_VERSION: Final = 1
_MODEL_KEYS: Final[tuple[str, ...]] = (
    "router",
    "classifier",
    "answer",
    "embeddings",
    "judge",
)

# Metric keys `headline_rows`/`_notes_section` read per dataset (*Comparison
# Output* section 5, *Validation Rules* "Metric values" row): a missing key or
# wrong type here must surface as the same `ComparisonError` as any other
# structural problem, never an unhandled `KeyError`/`TypeError` from
# `headline_rows`. Counts are always an int; rates are a rate computed by
# `evals.metrics.rate`, which is `None` on a zero denominator.
_COUNT_METRIC_KEYS: Final[dict[DatasetName, tuple[str, ...]]] = {
    "router": ("n",),
    "rules_qa": ("n", "answerable_n", "unanswerable_n", "judge_errors"),
    "move_classification": ("n",),
}
_RATE_METRIC_KEYS: Final[dict[DatasetName, tuple[str, ...]]] = {
    "router": ("accuracy",),
    "rules_qa": (
        "recall_at_k",
        "citation_validity_rate",
        "key_fact_coverage",
        "correct_refusal_rate",
    ),
    "move_classification": (
        "accuracy",
        "no_move_precision",
        "no_move_recall",
        "clarification_rate",
    ),
}

_ROUTER: Final[DatasetName] = "router"
_RULES: Final[DatasetName] = "rules_qa"
_MOVE: Final[DatasetName] = "move_classification"
_NO_MOVE: Final = "no_move"


class ComparisonError(Exception):
    """A report failed validation, or two or more reports are not comparable
    (the CLI, added in a later story, exits `2` on this)."""


@dataclass(frozen=True, slots=True)
class LoadedReport:
    path: Path
    label: str
    data: Mapping[str, JsonValue]


class _StructureError(Exception):
    """Carries the dotted key path of the first structural problem found by
    `_check_structure`; caught only inside `load_report`."""


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require(condition: bool, dotted_path: str) -> None:
    if not condition:
        raise _StructureError(dotted_path)


def _check_structure(data: Mapping[str, object]) -> None:
    """Spec 009 Report JSON shape, the fields this module reads (Validation
    Rules, "Report | structure" row). Raises `_StructureError` with the first
    violation's dotted key path."""
    _require(isinstance(data.get("run_id"), str), "run_id")
    _require(isinstance(data.get("started_at"), str), "started_at")
    git_commit = data.get("git_commit")
    _require(git_commit is None or isinstance(git_commit, str), "git_commit")

    config = data.get("config")
    _require(isinstance(config, dict), "config")
    config = cast(Mapping[str, object], config)
    _require(isinstance(config.get("name"), str), "config.name")

    models = config.get("models")
    _require(isinstance(models, dict), "config.models")
    models = cast(Mapping[str, object], models)
    for key in _MODEL_KEYS:
        _require(isinstance(models.get(key), str), f"config.models.{key}")

    _require(isinstance(config.get("graph"), dict), "config.graph")

    budget = data.get("budget")
    _require(isinstance(budget, dict), "budget")
    budget = cast(Mapping[str, object], budget)
    _require(_is_number(budget.get("spent_usd")), "budget.spent_usd")

    datasets = data.get("datasets")
    _require(isinstance(datasets, dict), "datasets")
    datasets = cast(Mapping[str, object], datasets)
    _require(len(datasets) > 0, "datasets")
    for name, raw_entry in datasets.items():
        _require(name in DATASET_ORDER, f"datasets.{name}")
        _require(isinstance(raw_entry, dict), f"datasets.{name}")
        entry = cast(Mapping[str, object], raw_entry)
        _require(isinstance(entry.get("sha256"), str), f"datasets.{name}.sha256")
        _require(
            isinstance(entry.get("rows"), int)
            and not isinstance(entry.get("rows"), bool),
            f"datasets.{name}.rows",
        )
        metrics = entry.get("metrics")
        _require(isinstance(metrics, dict), f"datasets.{name}.metrics")
        metrics = cast(Mapping[str, object], metrics)
        dataset_name = cast(DatasetName, name)
        for key in _COUNT_METRIC_KEYS.get(dataset_name, ()):
            _require(key in metrics, f"datasets.{name}.metrics.{key}")
            value = metrics.get(key)
            _require(
                isinstance(value, int) and not isinstance(value, bool),
                f"datasets.{name}.metrics.{key}",
            )
        for key in _RATE_METRIC_KEYS.get(dataset_name, ()):
            _require(key in metrics, f"datasets.{name}.metrics.{key}")
            value = metrics.get(key)
            _require(
                value is None or _is_number(value), f"datasets.{name}.metrics.{key}"
            )

        cases = entry.get("cases")
        _require(isinstance(cases, list), f"datasets.{name}.cases")
        for index, raw_case in enumerate(cast(list[object], cases)):
            case_path = f"datasets.{name}.cases[{index}]"
            _require(isinstance(raw_case, dict), case_path)
            case = cast(Mapping[str, object], raw_case)
            _require(isinstance(case.get("id"), str), f"{case_path}.id")
            intent = case.get("intent")
            _require(intent is None or isinstance(intent, str), f"{case_path}.intent")
            _require(_is_number(case.get("latency_ms")), f"{case_path}.latency_ms")
            cost_usd = case.get("cost_usd")
            _require(cost_usd is None or _is_number(cost_usd), f"{case_path}.cost_usd")


def load_report(path: Path) -> Mapping[str, JsonValue]:
    """Read and validate `path` as a spec 009 report (Validation Rules,
    checked in the documented order: existence, JSON, schema version, status,
    labels, structure). Raises `ComparisonError` with the message prefix
    documented for each failure."""
    if not path.is_file():
        raise ComparisonError(f"{path}: no such report file")

    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ComparisonError(f"{path}: not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ComparisonError(f"{path}: not valid JSON")
    data = cast(Mapping[str, JsonValue], parsed)

    schema_version = data.get("schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise ComparisonError(
            f"{path}: unsupported report schema_version {schema_version}"
        )

    status = data.get("status")
    if status != "completed":
        raise ComparisonError(
            f"{path}: report status is {status}; only completed runs can be compared"
        )

    labels = data.get("labels")
    reviewed = isinstance(labels, dict) and labels.get("all_rows_reviewed") is True
    if not reviewed:
        raise ComparisonError(f"{path}: report is not based on fully reviewed datasets")

    try:
        _check_structure(cast(Mapping[str, object], data))
    except _StructureError as exc:
        raise ComparisonError(f"{path}: not a spec 009 report ({exc})") from exc

    return data


def _config(report: LoadedReport) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], report.data["config"])


def _models(report: LoadedReport) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], _config(report)["models"])


def _graph(report: LoadedReport) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], _config(report)["graph"])


def _datasets(report: LoadedReport) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], report.data["datasets"])


def _dataset_entry(report: LoadedReport, name: DatasetName) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], _datasets(report)[name])


def _metrics(report: LoadedReport, name: DatasetName) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], _dataset_entry(report, name)["metrics"])


def _cases(
    report: LoadedReport, name: DatasetName
) -> Sequence[Mapping[str, JsonValue]]:
    return cast(
        Sequence[Mapping[str, JsonValue]], _dataset_entry(report, name)["cases"]
    )


def assign_labels(
    paths: Sequence[Path], reports: Sequence[Mapping[str, JsonValue]]
) -> tuple[LoadedReport, ...]:
    """Column labels (D13): each report's `config.name`, or - when two or more
    reports share a config name - `<name>-<first 6 hex of run_id>` for every
    report with that name."""
    names = [
        cast(str, cast(Mapping[str, JsonValue], r["config"])["name"]) for r in reports
    ]
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1

    labelled: list[LoadedReport] = []
    for path, data, name in zip(paths, reports, names, strict=True):
        if counts[name] > 1:
            run_id = cast(str, data["run_id"])
            label = f"{name}-{run_id[:6]}"
        else:
            label = name
        labelled.append(LoadedReport(path=path, label=label, data=data))
    return tuple(labelled)


def check_comparable(
    reports: Sequence[LoadedReport],
) -> tuple[tuple[DatasetName, ...], tuple[DatasetName, ...]]:
    """The comparability gate (D6, D7): equal judge models, at least one
    shared dataset, and equal `sha256` for every shared dataset. Returns
    `(shared, skipped)` dataset names in `DATASET_ORDER`. Raises
    `ComparisonError` on the first violation (judge, then shared datasets,
    then hashes)."""
    judges = {report.label: cast(str, _models(report)["judge"]) for report in reports}
    if len(set(judges.values())) > 1:
        pairs = ", ".join(f"{label}: {judge}" for label, judge in judges.items())
        raise ComparisonError(
            f"reports use different judge models ({pairs}); "
            "key-fact coverage is not comparable"
        )

    dataset_sets: list[set[str]] = [set(_datasets(report).keys()) for report in reports]
    shared_names: set[str] = dataset_sets[0].intersection(*dataset_sets[1:])
    all_names: set[str] = dataset_sets[0].union(*dataset_sets[1:])
    if not shared_names:
        raise ComparisonError("no dataset is present in every report")

    for name in DATASET_ORDER:
        if name not in shared_names:
            continue
        hashes = [
            cast(str, _dataset_entry(report, name)["sha256"]) for report in reports
        ]
        if len(set(hashes)) > 1:
            prefixes = " vs ".join(h[:12] for h in hashes)
            raise ComparisonError(
                f"{name} labels differ between reports (sha256 {prefixes}); "
                "re-run on the same dataset files"
            )

    shared = tuple(n for n in DATASET_ORDER if n in shared_names)
    skipped = tuple(
        n for n in DATASET_ORDER if n in all_names and n not in shared_names
    )
    return cast(tuple[DatasetName, ...], shared), cast(tuple[DatasetName, ...], skipped)


Unit = Literal["rate", "usd", "ms"]


@dataclass(frozen=True, slots=True)
class MetricRow:
    label: str
    unit: Unit
    cases: int | None
    values: tuple[float | None, ...]


def _recall_label(reports: Sequence[LoadedReport]) -> str:
    ks = {cast(int, _graph(report)["retrieval_k"]) for report in reports}
    if len(ks) > 1:
        return "Retrieval recall@k (k differs, see Configurations)"
    return f"Retrieval recall@{next(iter(ks))}"


def _shared_cases(
    report: LoadedReport, shared: Sequence[DatasetName]
) -> list[Mapping[str, JsonValue]]:
    result: list[Mapping[str, JsonValue]] = []
    for name in shared:
        result.extend(_cases(report, name))
    return result


def _cost_values(cases: Sequence[Mapping[str, JsonValue]]) -> list[float]:
    return [
        cast(float, case["cost_usd"])
        for case in cases
        if case.get("cost_usd") is not None
    ]


def _mean_or_none(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _cost_row(
    label: str,
    reports: Sequence[LoadedReport],
    shared: Sequence[DatasetName],
    *,
    intent: str | None,
    cases: int | None,
) -> MetricRow:
    values: list[float | None] = []
    for report in reports:
        report_cases = _shared_cases(report, shared)
        if intent is not None:
            report_cases = [c for c in report_cases if c.get("intent") == intent]
        values.append(_mean_or_none(_cost_values(report_cases)))
    return MetricRow(label=label, unit="usd", cases=cases, values=tuple(values))


def _latency_row(
    label: str,
    p: float,
    reports: Sequence[LoadedReport],
    shared: Sequence[DatasetName],
    cases: int,
) -> MetricRow:
    values = tuple(
        percentile(
            [cast(float, c["latency_ms"]) for c in _shared_cases(report, shared)], p
        )
        for report in reports
    )
    return MetricRow(label=label, unit="ms", cases=cases, values=values)


def headline_rows(
    reports: Sequence[LoadedReport], shared: Sequence[DatasetName]
) -> tuple[MetricRow, ...]:
    """The fixed headline metrics (*Comparison Output* section 5), restricted
    to the rows whose dataset is shared; the cost and latency rows are always
    present. Values come from each report's `metrics`, except cost and
    latency, which are recomputed from `cases[]` over the shared datasets
    (D9). `Cases` values come from the reference report (`reports[0]`)."""
    reference = reports[0]
    shared_set = set(shared)
    rows: list[MetricRow] = []

    def rate_row(label: str, name: DatasetName, key: str, cases: int | None) -> None:
        values = tuple(
            cast(float | None, _metrics(report, name)[key]) for report in reports
        )
        rows.append(MetricRow(label=label, unit="rate", cases=cases, values=values))

    if _ROUTER in shared_set:
        router_n = cast(int, _metrics(reference, _ROUTER)["n"])
        rate_row("Router accuracy", _ROUTER, "accuracy", router_n)

    if _RULES in shared_set:
        rules_metrics = _metrics(reference, _RULES)
        answerable_n = cast(int, rules_metrics["answerable_n"])
        unanswerable_n = cast(int, rules_metrics["unanswerable_n"])
        rules_n = cast(int, rules_metrics["n"])
        rate_row(_recall_label(reports), _RULES, "recall_at_k", answerable_n)
        rate_row("Citation validity", _RULES, "citation_validity_rate", rules_n)
        rate_row("Key-fact coverage", _RULES, "key_fact_coverage", answerable_n)
        rate_row("Correct refusals", _RULES, "correct_refusal_rate", unanswerable_n)

    if _MOVE in shared_set:
        move_n = cast(int, _metrics(reference, _MOVE)["n"])
        no_move_recall_cases = sum(
            1
            for case in _cases(reference, _MOVE)
            if case.get("expected_move_id") == _NO_MOVE
        )
        rate_row("Move accuracy", _MOVE, "accuracy", move_n)
        rate_row("no_move precision", _MOVE, "no_move_precision", None)
        rate_row("no_move recall", _MOVE, "no_move_recall", no_move_recall_cases)
        rate_row("Clarification rate", _MOVE, "clarification_rate", move_n)

    total_shared_cases = sum(len(_cases(reference, name)) for name in shared)
    reference_shared_cases = _shared_cases(reference, shared)
    rules_question_count = sum(
        1 for c in reference_shared_cases if c.get("intent") == "rules_question"
    )
    action_count = sum(
        1 for c in reference_shared_cases if c.get("intent") == "action_description"
    )

    rows.append(
        _cost_row(
            "Cost per query", reports, shared, intent=None, cases=total_shared_cases
        )
    )
    rows.append(
        _cost_row(
            "Cost per rules question",
            reports,
            shared,
            intent="rules_question",
            cases=rules_question_count,
        )
    )
    rows.append(
        _cost_row(
            "Cost per action description",
            reports,
            shared,
            intent="action_description",
            cases=action_count,
        )
    )
    rows.append(_latency_row("Latency p50", 50, reports, shared, total_shared_cases))
    rows.append(_latency_row("Latency p95", 95, reports, shared, total_shared_cases))

    return tuple(rows)


def format_value(unit: Unit, value: float | None) -> str:
    """One report's value, formatted per *Comparison Output*'s formatting
    table. `None` renders `"n/a"`."""
    if value is None:
        return "n/a"
    if unit == "rate":
        return f"{value * 100:.1f}%"
    if unit == "usd":
        return f"${value:.5f}"
    return f"{value:.0f} ms"


def format_delta(unit: Unit, reference: float | None, value: float | None) -> str:
    """`value - reference`, formatted per *Comparison Output*'s formatting
    table. `None` on either side renders `"n/a"`."""
    if reference is None or value is None:
        return "n/a"
    delta = value - reference
    if unit == "rate":
        return f"{delta * 100:+.1f} pp"
    if unit == "usd":
        sign = "-" if delta < 0 else "+"
        text = f"{sign}${abs(delta):.5f}"
        if reference != 0:
            text += f" ({delta / reference * 100:+.0f}%)"
        return text
    return f"{delta:+.0f} ms"


@dataclass(frozen=True, slots=True)
class CaseFlips:
    dataset: DatasetName
    reference_only: tuple[str, ...]
    candidate_only: tuple[str, ...]


def case_flips(
    reference: LoadedReport, candidate: LoadedReport, dataset: DatasetName
) -> CaseFlips:
    """Ids correct only in `reference` and ids correct only in `candidate`
    (D10), matched by `id` in `reference`'s file order. An id missing from
    either report is ignored."""
    candidate_cases = {
        cast(str, case["id"]): case for case in _cases(candidate, dataset)
    }
    reference_only: list[str] = []
    candidate_only: list[str] = []
    for case in _cases(reference, dataset):
        case_id = cast(str, case["id"])
        candidate_case = candidate_cases.get(case_id)
        if candidate_case is None:
            continue
        reference_correct = bool(case.get("correct"))
        candidate_correct = bool(candidate_case.get("correct"))
        if reference_correct and not candidate_correct:
            reference_only.append(case_id)
        elif candidate_correct and not reference_correct:
            candidate_only.append(case_id)
    return CaseFlips(
        dataset=dataset,
        reference_only=tuple(reference_only),
        candidate_only=tuple(candidate_only),
    )


def config_diff(
    reports: Sequence[LoadedReport],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Settings that are not identical across `reports`: `models.*` keys in
    spec 009 order, then `graph.*` keys sorted, each value rendered with
    `str()`. A key whose values are all equal is omitted (the judge is always
    equal, per `check_comparable`, so `models.judge` never appears)."""
    rows: list[tuple[str, tuple[str, ...]]] = []
    for key in _MODEL_KEYS:
        values = tuple(str(_models(report)[key]) for report in reports)
        if len(set(values)) > 1:
            rows.append((f"models.{key}", values))

    graph_keys: set[str] = set()
    for report in reports:
        graph_keys.update(_graph(report).keys())
    for key in sorted(graph_keys):
        values = tuple(str(_graph(report).get(key)) for report in reports)
        if len(set(values)) > 1:
            rows.append((f"graph.{key}", values))

    return tuple(rows)


def _format_cases(cases: int | None) -> str:
    return "—" if cases is None else str(cases)


def _format_ids(ids: Sequence[str]) -> str:
    if not ids:
        return "none"
    shown = ids[:MAX_FLIP_IDS]
    text = ", ".join(shown)
    remaining = len(ids) - len(shown)
    if remaining:
        text += f", … and {remaining} more"
    return text


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _results_header(labels: Sequence[str]) -> list[str]:
    cols = ["Metric", "Cases", labels[0]]
    if len(labels) == 2:
        cols.extend([labels[1], "Δ"])
    else:
        for label in labels[1:]:
            cols.extend([label, f"Δ {label}"])
    return cols


def _results_row(row: MetricRow, labels: Sequence[str]) -> list[str]:
    cells = [row.label, _format_cases(row.cases), format_value(row.unit, row.values[0])]
    if len(labels) == 2:
        cells.append(format_value(row.unit, row.values[1]))
        cells.append(format_delta(row.unit, row.values[0], row.values[1]))
    else:
        for value in row.values[1:]:
            cells.append(format_value(row.unit, value))
            cells.append(format_delta(row.unit, row.values[0], value))
    return cells


def _reports_section(reports: Sequence[LoadedReport]) -> str:
    lines = [
        "## Reports",
        "",
        _row(
            ["Config", "Report", "Run id", "Started (UTC)", "Git commit", "Eval spend"]
        ),
        _row(["---"] * 6),
    ]
    commits: list[str | None] = []
    for report in reports:
        commit = cast("str | None", report.data.get("git_commit"))
        commits.append(commit)
        budget = cast(Mapping[str, JsonValue], report.data["budget"])
        spent = cast(float, budget["spent_usd"])
        lines.append(
            _row(
                [
                    report.label,
                    str(report.path),
                    cast(str, report.data["run_id"]),
                    cast(str, report.data["started_at"]),
                    commit[:12] if commit else "n/a",
                    f"${spent:.4f}",
                ]
            )
        )
    if len(set(commits)) > 1:
        lines.append("")
        lines.append(
            "**Note:** reports come from different commits; deltas may include "
            "code changes, not only configuration."
        )
    return "\n".join(lines)


def _configurations_section(reports: Sequence[LoadedReport]) -> str:
    diff = config_diff(reports)
    labels = [report.label for report in reports]
    lines = ["## Configurations", ""]
    if diff:
        lines.append(_row(["Setting", *labels]))
        lines.append(_row(["---"] * (len(labels) + 1)))
        for setting, values in diff:
            lines.append(_row([f"`{setting}`", *(f"`{v}`" for v in values)]))
    else:
        lines.append(
            "No setting differs: these are repeated runs of the same configuration."
        )
    lines.append("")
    judge = cast(str, _models(reports[0])["judge"])
    lines.append(f"Judge (identical in all reports): `{judge}`.")
    return "\n".join(lines)


def _results_section(
    reports: Sequence[LoadedReport], shared: Sequence[DatasetName]
) -> str:
    labels = [report.label for report in reports]
    rows = headline_rows(reports, shared)
    header = _results_header(labels)
    lines = [
        "## Results",
        "",
        TABLE_START,
        _row(header),
        _row(["---"] * len(header)),
    ]
    for row in rows:
        lines.append(_row(_results_row(row, labels)))
    lines.append(TABLE_END)
    return "\n".join(lines)


_FLIP_DATASETS: Final[tuple[DatasetName, ...]] = (_ROUTER, _MOVE)


def _changed_cases_section(
    reports: Sequence[LoadedReport], shared: Sequence[DatasetName]
) -> str:
    shared_set = set(shared)
    flip_datasets: list[DatasetName] = [
        name for name in _FLIP_DATASETS if name in shared_set
    ]
    if not flip_datasets:
        return "## Changed cases\n\nNo router or move cases to compare."

    reference = reports[0]
    lines = ["## Changed cases", ""]
    for dataset in flip_datasets:
        for candidate in reports[1:]:
            flips = case_flips(reference, candidate, dataset)
            lines.append(f"### {dataset}: {reference.label} vs {candidate.label}")
            lines.append(
                f"Correct only in {reference.label} "
                f"({len(flips.reference_only)}): {_format_ids(flips.reference_only)}"
            )
            lines.append(
                f"Correct only in {candidate.label} "
                f"({len(flips.candidate_only)}): {_format_ids(flips.candidate_only)}"
            )
            lines.append("")
    return "\n".join(lines).rstrip("\n")


def _notes_section(
    reports: Sequence[LoadedReport],
    shared: Sequence[DatasetName],
    skipped: Sequence[DatasetName],
) -> str:
    reference = reports[0]
    lines = [
        "## Notes",
        "",
        f"- Datasets compared: {', '.join(shared)}.",
    ]
    if skipped:
        lines.append(f"- Skipped (not in every report): {', '.join(skipped)}.")

    for name in shared:
        rows = cast(int, _dataset_entry(reference, name)["rows"])
        pp = 100 / rows if rows else 0.0
        lines.append(f"- {name}: {rows} cases; one case = {pp:.1f} pp.")

    judge_error_entries = [
        f"{report.label}: {judge_errors}"
        for report in reports
        if _RULES in _datasets(report)
        for judge_errors in (
            cast(int, _metrics(report, _RULES).get("judge_errors", 0)),
        )
        if judge_errors > 0
    ]
    if judge_error_entries:
        lines.append(
            "- Judge errors (excluded from key-fact coverage): "
            + ", ".join(judge_error_entries)
            + "."
        )

    lines.append(
        "- Differences of one or two cases are within run-to-run noise; check "
        "Changed cases before attributing a delta to the configuration."
    )
    return "\n".join(lines)


def render_comparison(
    reports: Sequence[LoadedReport],
    shared: Sequence[DatasetName],
    skipped: Sequence[DatasetName],
    generated_at: datetime,
) -> str:
    """The seven-section Markdown comparison (*Comparison Output*), in order:
    title, generated line, Reports, Configurations, Results, Changed cases,
    Notes."""
    labels = [report.label for report in reports]
    title = "# Eval comparison: " + " vs ".join(labels)
    generated_line = (
        f"Generated {generated_at.isoformat()} by `evals/compare.py`. "
        f"Reference: `{labels[0]}`."
    )
    sections = [
        title,
        generated_line,
        _reports_section(reports),
        _configurations_section(reports),
        _results_section(reports, shared),
        _changed_cases_section(reports, shared),
        _notes_section(reports, shared, skipped),
    ]
    return "\n\n".join(sections) + "\n"


def comparison_path(comparisons_dir: Path, date: str, labels: Sequence[str]) -> Path:
    """`<comparisons_dir>/<date>-<label1>-vs-<label2>[-vs-…].md`, suffixed
    `-2`, `-3`… on collision (D11; spec 009 D12 rule)."""
    base = f"{date}-" + "-vs-".join(labels)
    path = comparisons_dir / f"{base}.md"
    if not path.exists():
        return path

    suffix = 2
    while True:
        path = comparisons_dir / f"{base}-{suffix}.md"
        if not path.exists():
            return path
        suffix += 1


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_args(argv: Sequence[str] | None) -> list[Path]:
    parser = argparse.ArgumentParser(prog="python -m evals.compare")
    parser.add_argument("reports", nargs="+")
    args = parser.parse_args(argv)
    return [Path(value) for value in cast("list[str]", args.reports)]


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return str(path)


def main(
    argv: Sequence[str] | None = None,
    *,
    comparisons_dir: Path = DEFAULT_COMPARISONS_DIR,
    now: Callable[[], datetime] = _utc_now,
) -> int:
    """The CLI entry point (*Configuration -> CLI*). Runs the checks in
    *Validation Rules* `main` check order: argument count, then each report in
    argument order (existence, JSON, schema version, status, labels,
    structure), then comparability (judge, shared datasets, hashes). The
    first failure prints `compare: error: <message>` to stderr and returns
    `2` without writing anything; success prints `compare: wrote <path>` and
    returns `0`."""
    paths = _parse_args(argv)

    if not MIN_REPORTS <= len(paths) <= MAX_REPORTS:
        print(
            f"compare: error: expected {MIN_REPORTS} to {MAX_REPORTS} report "
            f"files, got {len(paths)}",
            file=sys.stderr,
        )
        return 2

    raw_reports: list[Mapping[str, JsonValue]] = []
    try:
        for path in paths:
            raw_reports.append(load_report(path))
    except ComparisonError as exc:
        print(f"compare: error: {exc}", file=sys.stderr)
        return 2

    reports = assign_labels(paths, raw_reports)

    try:
        shared, skipped = check_comparable(reports)
    except ComparisonError as exc:
        print(f"compare: error: {exc}", file=sys.stderr)
        return 2

    generated_at = now()
    rendered = render_comparison(reports, shared, skipped, generated_at)

    date = generated_at.strftime("%Y-%m-%d")
    labels = [report.label for report in reports]
    out_path = comparison_path(comparisons_dir, date, labels)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    print(f"compare: wrote {_display_path(out_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
