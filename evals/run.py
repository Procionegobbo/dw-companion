"""The eval CLI (spec 009 *Architecture / Design Overview*, *Configuration -> CLI*).

`main` is the single entry point: `uv run --env-file .env python -m evals.run
--config NAME [--dataset {all,router,rules_qa,move_classification}]
[--budget-usd X]`. It runs the checks in *Validation Rules -> Check order in
`main`* in order (arguments, config, known ids, dataset schema, R-LABEL, env,
services, pre-flight budget) and stops at the first failure; stages 1-6 make
no network call and build nothing. `default_services_factory` wires the real
runtime (`backend.composition.build_runtime`) and eval support (judge client +
prices, `build_eval_support`) behind the `ServicesFactory` seam, so tests can
substitute an entirely fake one (`evals/tests/helpers.py` `fake_services`)
without this module ever importing a vendor SDK (D8): it only imports the
`HttpClientSeam`/`SpanExporterSeam` type aliases `backend/composition.py`
re-exports for that purpose.

`TRACE_NAME` is this module's constant (spec 009 Constants); `evals/report.py`
imports it lazily, inside `build_report`, to avoid a circular import (see the
comment there).
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, cast
from uuid import uuid4

from backend.adapters.openrouter import ModelPrice
from backend.composition import (
    DEFAULT_INDEX_DIR,
    DEFAULT_NORMALIZED_DIR,
    REPO_ROOT,
    ConfigError,
    HttpClientSeam,
    Runtime,
    Settings,
    SpanExporterSeam,
    TraceOptions,
    build_eval_support,
    build_runtime,
)
from backend.ports.errors import PortError
from backend.ports.llm import LLMClient
from backend.ports.tracer import Tracer
from evals.budget import DEFAULT_BUDGET_USD, MAX_BUDGET_USD, estimate
from evals.collector import CollectingTracer
from evals.config import ConfigFileError, EvalConfig, load_config, model_env
from evals.datasets import (
    DATASET_ORDER,
    Dataset,
    DatasetError,
    DatasetName,
    UnreviewedRowsError,
    ensure_reviewed,
    known_ids_from,
    load_dataset,
)
from evals.report import build_report, report_paths, write_report
from evals.runner import RunOutcome, run_datasets

TRACE_NAME: Final = "eval_turn"

DEFAULT_CONFIGS_DIR: Final = REPO_ROOT / "evals" / "configs"
DEFAULT_DATASETS_DIR: Final = REPO_ROOT / "evals" / "datasets"
DEFAULT_REPORTS_DIR: Final = REPO_ROOT / "evals" / "reports"

_GIT_COMMIT_TIMEOUT_S: Final = 5


@dataclass(frozen=True, slots=True)
class EvalPaths:
    configs_dir: Path = DEFAULT_CONFIGS_DIR
    datasets_dir: Path = DEFAULT_DATASETS_DIR
    reports_dir: Path = DEFAULT_REPORTS_DIR
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR
    index_dir: Path = DEFAULT_INDEX_DIR


@dataclass(frozen=True, slots=True)
class EvalServices:
    """What one eval run needs besides the datasets and config: a wired
    `Runtime` (assistant + tee'd tracer), the judge client, model prices for
    the budget guard, and `aclose` to close the runtime, close the judge
    client and flush traces (idempotent on the underlying resources)."""

    runtime: Runtime
    judge: LLMClient
    prices: Mapping[str, ModelPrice]
    aclose: Callable[[], Awaitable[None]]


ServicesFactory = Callable[
    [EvalConfig, Settings, TraceOptions, Tracer, EvalPaths], Awaitable[EvalServices]
]


async def default_services_factory(
    config: EvalConfig,
    settings: Settings,
    trace_options: TraceOptions,
    tap: Tracer,
    paths: EvalPaths,
    *,
    http_client: HttpClientSeam | None = None,
    span_exporter: SpanExporterSeam | None = None,
) -> EvalServices:
    """Wires the real runtime and eval support for one run (spec 009 Data
    Model paragraph after `evals/run.py`). `http_client`/`span_exporter` are
    test seams, passed through unchanged to `build_runtime`/`build_eval_support`."""
    runtime = build_runtime(
        settings,
        index_dir=paths.index_dir,
        normalized_dir=paths.normalized_dir,
        http_client=http_client,
        span_exporter=span_exporter,
        graph_settings=config.graph,
        trace_options=trace_options,
        tracer_tap=tap,
    )
    support = await build_eval_support(
        settings,
        config.models.judge,
        {
            config.models.router,
            config.models.classifier,
            config.models.answer,
            config.models.judge,
        },
        http_client=http_client,
    )

    async def aclose() -> None:
        await support.aclose()
        await runtime.aclose()

    return EvalServices(
        runtime=runtime, judge=support.judge, prices=support.prices, aclose=aclose
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


def _git_commit() -> str | None:
    """`git rev-parse HEAD`, 5 s timeout, `None` on any failure (D19)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_COMMIT_TIMEOUT_S,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def _parse_budget(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}") from exc
    if not math.isfinite(parsed) or not (0 < parsed <= MAX_BUDGET_USD):
        raise argparse.ArgumentTypeError(
            f"--budget-usd must be finite and in (0, {MAX_BUDGET_USD}], got {value!r}"
        )
    return parsed


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _format_unreviewed_error(exc: UnreviewedRowsError) -> str:
    plural = "row" if exc.count == 1 else "rows"
    ids_text = ", ".join(exc.ids)
    suffix = ", ..." if exc.count > len(exc.ids) else ""
    return (
        f"evals: error: {exc.dataset}.jsonl has {exc.count} unreviewed {plural}: "
        f"{ids_text}{suffix}"
    )


def _trace_options(
    config: EvalConfig, run_id: str, dataset_names: Sequence[DatasetName]
) -> TraceOptions:
    return TraceOptions(
        trace_name=TRACE_NAME,
        metadata={
            "eval_run_id": run_id,
            "eval_config": config.name,
            "eval_config_sha256": config.sha256[:12],
            "eval_datasets": ",".join(dataset_names),
            "model_router": config.models.router,
            "model_classifier": config.models.classifier,
            "model_answer": config.models.answer,
            "model_embeddings": config.models.embeddings,
            "model_judge": config.models.judge,
            "retrieval_k": str(config.graph.retrieval_k),
            "clarify_threshold": str(config.graph.clarify_threshold),
        },
        tags=("eval", f"config:{config.name}"),
    )


async def _run(
    *,
    config: EvalConfig,
    settings: Settings,
    paths: EvalPaths,
    datasets: Sequence[Dataset],
    budget_usd: float,
    trace_options: TraceOptions,
    run_id: str,
    started_at: datetime,
    now: Callable[[], datetime],
    new_id: Callable[[], str],
    clock: Callable[[], float],
    services_factory: ServicesFactory,
) -> int:
    tap = CollectingTracer()
    try:
        services = await services_factory(config, settings, trace_options, tap, paths)
    except (ConfigError, PortError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"evals: error: {exc}", file=sys.stderr)
        return 2

    try:
        estimated_usd = estimate(datasets, config, services.prices)
        print(
            f"evals: estimated max cost ${estimated_usd:.4f} (budget ${budget_usd:.2f})"
        )
        if estimated_usd > budget_usd:
            print(
                f"evals: error: estimated max cost ${estimated_usd:.4f} exceeds "
                f"budget ${budget_usd:.2f}",
                file=sys.stderr,
            )
            return 4

        outcome: RunOutcome = await run_datasets(
            datasets,
            config=config,
            assistant=services.runtime.assistant,
            tracer=services.runtime.tracer,
            collector=tap,
            judge=services.judge,
            prices=services.prices,
            budget_usd=budget_usd,
            run_id=run_id,
            new_id=new_id,
            clock=clock,
            progress=lambda message: print(f"evals: {message}"),
        )

        status: Literal["completed", "aborted_budget"] = (
            "aborted_budget" if outcome.aborted else "completed"
        )
        report = build_report(
            run_id=run_id,
            status=status,
            started_at=started_at,
            finished_at=now(),
            git_commit=_git_commit(),
            config=config,
            datasets=datasets,
            budget_usd=budget_usd,
            estimated_usd=estimated_usd,
            outcome=outcome,
        )
        date = started_at.strftime("%Y-%m-%d")
        json_path, md_path = report_paths(paths.reports_dir, date, config.name)
        write_report(report, json_path, md_path)

        print(f"evals: report {_relative_path(json_path)}")
        print(f"evals: langfuse session {run_id}")

        if outcome.aborted:
            total_completed = sum(len(records) for records in outcome.records.values())
            print(
                f"evals: error: budget backstop reached after {total_completed} "
                f"cases (${outcome.spent_usd:.4f} spent); partial report written",
                file=sys.stderr,
            )
            return 4
        return 0
    finally:
        await services.aclose()


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    paths: EvalPaths = EvalPaths(),  # noqa: B008 (frozen dataclass; spec 009 signature)
    services_factory: ServicesFactory = default_services_factory,
    now: Callable[[], datetime] = _utc_now,
    new_id: Callable[[], str] = _new_id,
    clock: Callable[[], float] = time.perf_counter,
) -> int:
    env = environ if environ is not None else os.environ

    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", choices=("all", *DATASET_ORDER), default="all")
    parser.add_argument("--budget-usd", type=_parse_budget, default=DEFAULT_BUDGET_USD)
    args = parser.parse_args(argv)

    # 2. config
    try:
        config = load_config(args.config, paths.configs_dir)
    except ConfigFileError as exc:
        print(f"evals: error: {exc}", file=sys.stderr)
        return 2

    # 3. known_ids_from(normalized_dir)
    try:
        known = known_ids_from(paths.normalized_dir)
    except (OSError, ValueError) as exc:
        print(f"evals: error: {exc}", file=sys.stderr)
        return 2

    selected_names: tuple[DatasetName, ...] = (
        DATASET_ORDER if args.dataset == "all" else (cast(DatasetName, args.dataset),)
    )

    # 4. dataset schema
    datasets: list[Dataset] = []
    try:
        for name in selected_names:
            dataset_path = paths.datasets_dir / f"{name}.jsonl"
            datasets.append(load_dataset(name, dataset_path, known))
    except (DatasetError, OSError) as exc:
        print(f"evals: error: {exc}", file=sys.stderr)
        return 2

    # 5. R-LABEL (first enforcement point; `run_datasets` re-checks as the second)
    try:
        for dataset in datasets:
            ensure_reviewed(dataset)
    except UnreviewedRowsError as exc:
        print(_format_unreviewed_error(exc), file=sys.stderr)
        return 3

    # 6. env
    merged_env = {**env, **model_env(config)}
    try:
        settings = Settings.from_env(merged_env)
    except ConfigError as exc:
        print(f"evals: error: {exc}", file=sys.stderr)
        return 2
    if settings.langfuse is None:
        print(
            "evals: error: eval runs must be traced: set LANGFUSE_PUBLIC_KEY and "
            "LANGFUSE_SECRET_KEY",
            file=sys.stderr,
        )
        return 2

    run_id = new_id()
    trace_options = _trace_options(config, run_id, selected_names)

    total_cases = sum(len(dataset.cases) for dataset in datasets)
    print(
        f"evals: config {config.name} (sha256 {config.sha256[:12]}), "
        f"datasets {','.join(selected_names)}, {total_cases} cases"
    )

    started_at = now()
    # 7. services; 8. pre-flight budget; then the run itself.
    return asyncio.run(
        _run(
            config=config,
            settings=settings,
            paths=paths,
            datasets=datasets,
            budget_usd=args.budget_usd,
            trace_options=trace_options,
            run_id=run_id,
            started_at=started_at,
            now=now,
            new_id=new_id,
            clock=clock,
            services_factory=services_factory,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
