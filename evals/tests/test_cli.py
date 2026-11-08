"""Tests for `evals/run.py`'s `main` (spec 009 *Architecture / Design Overview*,
*Configuration -> CLI*, rule R-LABEL's first enforcement point).

Most tests wire fakes through `evals/tests/helpers.py`'s `fake_services`, so no
network call is possible. `test_cli_end_to_end_with_mock_openrouter` is the one
wiring proof that exercises `default_services_factory` itself, over a mocked
OpenRouter transport (D16), to show the real seams fit together.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import cast

import pytest

from backend.adapters.openrouter import ModelPrice
from backend.adapters.retrieval.chunking import build_chunks
from backend.adapters.retrieval.index import write_index
from backend.adapters.tee_tracer import TeeTracer
from backend.composition import Runtime, Settings, TraceOptions
from backend.domain.rulebook import move_from_dict, section_from_dict
from backend.ports.errors import PortError
from backend.ports.llm import ModelRole
from backend.ports.retriever import RetrievedChunk
from backend.ports.tracer import Tracer
from backend.tests.adapter_helpers import (
    memory_exporter,
    mock_http,
    mock_openrouter_transport,
)
from backend.tests.fakes.embedder import FakeEmbedder
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.tracer import FakeTracer
from backend.tests.graph_helpers import (
    chunk,
    classifier_json,
    make_assistant,
    router_json,
)
from evals.config import EvalConfig
from evals.run import (
    EvalPaths,
    EvalServices,
    ServicesFactory,
    default_services_factory,
    main,
)

from .helpers import (
    FAKE_ENV,
    CostingLLMClient,
    fake_services,
    fixture_paths,
    move_row,
    router_row,
    rules_row,
    write_jsonl,
)


async def _never_called_factory(
    config: EvalConfig,
    settings: Settings,
    trace_options: TraceOptions,
    tap: Tracer,
    paths: EvalPaths,
) -> EvalServices:
    raise AssertionError("services factory should not have been called")


async def _noop_aclose() -> None:
    return None


def _costing_services(
    llm_script: Mapping[ModelRole, Sequence[str | PortError]],
    *,
    cost: float,
    chunks: Sequence[RetrievedChunk] = (),
) -> tuple[ServicesFactory, FakeTracer]:
    fake_tracer = FakeTracer()

    async def factory(
        config: EvalConfig,
        settings: Settings,
        trace_options: TraceOptions,
        tap: Tracer,
        paths: EvalPaths,
    ) -> EvalServices:
        tee = TeeTracer(fake_tracer, tap)
        llm = CostingLLMClient(FakeLLMClient(llm_script), cost)
        assistant, _ = make_assistant(
            llm, retriever=FakeRetriever(chunks), tracer=tee, settings=config.graph
        )
        runtime = Runtime(assistant, _noop_aclose, tracer=tee)
        judge = FakeLLMClient({"answer": []})
        prices = {
            model: ModelPrice(1e-6, 2e-6)
            for model in (
                config.models.router,
                config.models.classifier,
                config.models.answer,
                config.models.judge,
            )
        }
        return EvalServices(
            runtime=runtime, judge=judge, prices=prices, aclose=_noop_aclose
        )

    return factory, fake_tracer


def _tracking_aclose(
    factory: ServicesFactory,
) -> tuple[ServicesFactory, dict[str, int]]:
    calls = {"n": 0}

    async def tracking_factory(
        config: EvalConfig,
        settings: Settings,
        trace_options: TraceOptions,
        tap: Tracer,
        paths: EvalPaths,
    ) -> EvalServices:
        services = await factory(config, settings, trace_options, tap, paths)
        inner_aclose: Callable[[], Awaitable[None]] = services.aclose

        async def aclose() -> None:
            calls["n"] += 1
            await inner_aclose()

        return EvalServices(
            runtime=services.runtime,
            judge=services.judge,
            prices=services.prices,
            aclose=aclose,
        )

    return tracking_factory, calls


def test_cli_refuses_unreviewed_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "a router case", "rules_question")],
    )
    write_jsonl(
        paths.datasets_dir / "move_classification.jsonl",
        [move_row("move-001", "a move case", "hack-and-slash")],
    )
    write_jsonl(
        paths.datasets_dir / "rules_qa.jsonl",
        [rules_row("rules-001", "an unreviewed case", [], [], reviewed=False)],
    )

    code = main(
        ["--config", "test"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=_never_called_factory,
    )

    captured = capsys.readouterr()
    assert code == 3
    assert captured.err.startswith("evals: error: rules_qa.jsonl has 1 unreviewed row")
    assert list(paths.reports_dir.iterdir()) == []


def test_cli_refuses_missing_reviewed_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "a router case", "rules_question")],
    )
    write_jsonl(
        paths.datasets_dir / "move_classification.jsonl",
        [move_row("move-001", "a move case", "hack-and-slash")],
    )
    paths.datasets_dir.joinpath("rules_qa.jsonl").write_text(
        json.dumps(
            {
                "id": "rules-001",
                "message": "no reviewed key here",
                "expected_section_ids": [],
                "key_facts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(
        ["--config", "test"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=_never_called_factory,
    )

    captured = capsys.readouterr()
    assert code == 3
    assert captured.err.startswith("evals: error: rules_qa.jsonl has 1 unreviewed row")


def test_cli_single_unreviewed_row_blocks_all_datasets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "a router case", "rules_question")],
    )
    write_jsonl(
        paths.datasets_dir / "move_classification.jsonl",
        [move_row("move-001", "a move case", "hack-and-slash")],
    )
    write_jsonl(
        paths.datasets_dir / "rules_qa.jsonl",
        [rules_row("rules-001", "an unreviewed case", [], [], reviewed=False)],
    )

    code = main(
        ["--config", "test", "--dataset", "all"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=_never_called_factory,
    )

    assert code == 3
    captured = capsys.readouterr()
    assert "rules_qa.jsonl has 1 unreviewed row" in captured.err


def test_cli_has_no_unreviewed_override(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--config", "test", "--allow-unreviewed"],
            environ=FAKE_ENV,
            paths=paths,
            services_factory=_never_called_factory,
        )

    assert exc_info.value.code == 2


def test_cli_schema_error_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = fixture_paths(tmp_path)
    paths.datasets_dir.joinpath("router.jsonl").write_text(
        json.dumps({"id": "router-001", "expected_intent": "rules_question"}) + "\n",
        encoding="utf-8",
    )

    code = main(
        ["--config", "test", "--dataset", "router"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=_never_called_factory,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.startswith("evals: error:")


def test_cli_requires_langfuse_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "a router case", "rules_question")],
    )

    code = main(
        ["--config", "test", "--dataset", "router"],
        environ={"OPENROUTER_API_KEY": "k"},
        paths=paths,
        services_factory=_never_called_factory,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err == (
        "evals: error: eval runs must be traced: set LANGFUSE_PUBLIC_KEY and "
        "LANGFUSE_SECRET_KEY\n"
    )


def test_cli_preflight_budget_abort(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [router_row("router-001", "a router case", "out_of_scope")],
    )
    factory, _tracer = fake_services({}, [])

    code = main(
        ["--config", "test", "--dataset", "router", "--budget-usd", "0.01"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=factory,
    )

    assert code == 4
    assert list(paths.reports_dir.iterdir()) == []


@pytest.mark.parametrize("value", ["0", "-1", "51", "nan"])
def test_cli_budget_arg_bounds(tmp_path: Path, value: str) -> None:
    paths = fixture_paths(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--config", "test", f"--budget-usd={value}"],
            environ=FAKE_ENV,
            paths=paths,
            services_factory=_never_called_factory,
        )

    assert exc_info.value.code == 2


def test_cli_completed_run_writes_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
    )
    tracking_factory, aclose_calls = _tracking_aclose(factory)

    code = main(
        ["--config", "test"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=tracking_factory,
    )

    assert code == 0
    assert aclose_calls["n"] == 1

    report_files = sorted(paths.reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert paths.reports_dir.joinpath(report_files[0].stem + ".md").exists()

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 7
    assert lines[0].startswith("evals: config test (sha256 ")
    assert lines[0].endswith("datasets router,rules_qa,move_classification, 3 cases")
    assert lines[1].startswith("evals: estimated max cost $")
    assert lines[1].endswith("(budget $3.00)")
    assert lines[2].startswith("evals: router done: 1 cases, spent $")
    assert lines[3].startswith("evals: rules_qa done: 1 cases, spent $")
    assert lines[4].startswith("evals: move_classification done: 1 cases, spent $")
    assert lines[5].startswith("evals: report ")
    assert lines[6].startswith("evals: langfuse session ")


def test_cli_inflight_abort_writes_partial_report(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    write_jsonl(
        paths.datasets_dir / "router.jsonl",
        [
            router_row("router-001", "a router case", "out_of_scope"),
            router_row("router-002", "another router case", "out_of_scope"),
        ],
    )
    factory, _tracer = _costing_services(
        {"router": [router_json("out_of_scope"), router_json("out_of_scope")]},
        cost=5.0,
    )

    code = main(
        ["--config", "test", "--dataset", "router", "--budget-usd", "1.0"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=factory,
    )

    assert code == 4
    report_files = list(paths.reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert report["status"] == "aborted_budget"
    assert report["datasets"]["router"]["completed"] == 1


def _build_index(normalized_dir: Path, index_dir: Path, embedding_model: str) -> None:
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    chunks = build_chunks(sections, moves)
    embedder = FakeEmbedder(dim=64)
    vectors = asyncio.run(embedder.embed([c.index_text for c in chunks]))
    write_index(index_dir, chunks, vectors, embedding_model)


def _chat_response(model: str, _body: Mapping[str, object]) -> str:
    if model == "m-router":
        return router_json("rules_question")
    if model == "m-judge":
        return '{"facts": [{"index": 0, "present": true, "evidence": "deal damage"}]}'
    return "Hack and Slash lets you deal damage. [[moves/hack-and-slash]]"


def test_cli_end_to_end_with_mock_openrouter(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    _build_index(paths.normalized_dir, paths.index_dir, "m-embeddings")

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

    handler, requests = mock_openrouter_transport(
        prices={
            "m-router": ("0.000001", "0.000002"),
            "m-classifier": ("0.000001", "0.000002"),
            "m-answer": ("0.000001", "0.000002"),
            "m-judge": ("0.000003", "0.000004"),
        },
        chat_response=_chat_response,
    )

    http_client = mock_http(handler)
    exporter = memory_exporter()
    run_id = "ab" * 16

    code = main(
        ["--config", "test", "--dataset", "rules_qa"],
        environ=FAKE_ENV,
        paths=paths,
        services_factory=partial(
            default_services_factory, http_client=http_client, span_exporter=exporter
        ),
        new_id=lambda: run_id,
    )

    assert code == 0

    chat_models = [body["model"] for body in requests]
    assert chat_models.count("m-judge") == 1
    assert set(chat_models) <= {"m-router", "m-answer", "m-judge"}

    spans = exporter.get_finished_spans()
    assert spans
    attrs_list: list[Mapping[str, object]] = [
        span.attributes for span in spans if span.attributes is not None
    ]
    assert attrs_list

    trace_names = {str(attrs["langfuse.trace.name"]) for attrs in attrs_list}
    assert trace_names == {"eval_turn"}

    session_ids = {str(attrs["session.id"]) for attrs in attrs_list}
    assert session_ids == {run_id}

    eval_configs = {
        json.loads(cast(str, attrs["langfuse.trace.metadata.eval_config"]))
        for attrs in attrs_list
        if "langfuse.trace.metadata.eval_config" in attrs
    }
    assert eval_configs == {"test"}

    model_judges = {
        json.loads(cast(str, attrs["langfuse.trace.metadata.model_judge"]))
        for attrs in attrs_list
        if "langfuse.trace.metadata.model_judge" in attrs
    }
    assert model_judges == {"m-judge"}

    all_tags: set[str] = set()
    for attrs in attrs_list:
        tags = attrs.get("langfuse.trace.tags")
        if isinstance(tags, Sequence) and not isinstance(tags, str):
            all_tags.update(str(tag) for tag in cast(Sequence[object], tags))
    assert "config:test" in all_tags

    span_names = {span.name for span in spans}
    assert "eval_case" in span_names

    generation_names = {
        span.name
        for span in spans
        if span.attributes is not None
        and span.attributes.get("langfuse.observation.type") == "generation"
    }
    assert "judge_key_facts" in generation_names
