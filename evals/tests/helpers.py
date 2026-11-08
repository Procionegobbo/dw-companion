"""Shared test builders for `evals/tests/` (spec 009 Testing). Not collected by pytest
(no `test_` prefix).

`reviewed=True` exists only in these builders, used to write `tmp_path` fixture files -
never under `evals/datasets/` (rule R-LABEL point 2).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from backend.adapters.openrouter import ModelPrice
from backend.adapters.tee_tracer import TeeTracer
from backend.composition import Runtime, Settings, TraceOptions
from backend.ports.errors import PortError
from backend.ports.llm import LLMClient, LLMRequest, LLMResponse, ModelRole
from backend.ports.retriever import RetrievedChunk
from backend.ports.tracer import Tracer
from backend.tests.adapter_helpers import mini_normalized
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.tracer import FakeTracer
from backend.tests.graph_helpers import make_assistant
from evals.config import EvalConfig
from evals.run import EvalPaths, EvalServices, ServicesFactory

FAKE_ENV: Final[dict[str, str]] = {
    "OPENROUTER_API_KEY": "k",
    "LANGFUSE_PUBLIC_KEY": "pk",
    "LANGFUSE_SECRET_KEY": "sk",
}

_TEST_CONFIG_TOML: Final = """[models]
router = "m-router"
classifier = "m-classifier"
answer = "m-answer"
embeddings = "m-embeddings"
judge = "m-judge"
"""

_DEFAULT_PRICE: Final = ModelPrice(
    prompt_usd_per_token=1e-6, completion_usd_per_token=2e-6
)
_DEFAULT_PRICES: Final[dict[str, ModelPrice]] = {
    "m-router": _DEFAULT_PRICE,
    "m-classifier": _DEFAULT_PRICE,
    "m-answer": _DEFAULT_PRICE,
    "m-judge": _DEFAULT_PRICE,
}


def write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    """Write `rows` as one JSON object per line, UTF-8, LF, with a trailing newline."""
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def router_row(
    id: str, message: str, intent: str, *, reviewed: bool = True
) -> dict[str, object]:
    return {
        "id": id,
        "message": message,
        "expected_intent": intent,
        "reviewed": reviewed,
    }


def rules_row(
    id: str,
    message: str,
    expected_section_ids: Sequence[str],
    key_facts: Sequence[str],
    *,
    reviewed: bool = True,
) -> dict[str, object]:
    return {
        "id": id,
        "message": message,
        "expected_section_ids": list(expected_section_ids),
        "key_facts": list(key_facts),
        "reviewed": reviewed,
    }


def move_row(
    id: str,
    message: str,
    expected_move_id: str,
    acceptable_alternatives: Sequence[str] = (),
    *,
    reviewed: bool = True,
) -> dict[str, object]:
    return {
        "id": id,
        "message": message,
        "expected_move_id": expected_move_id,
        "acceptable_alternatives": list(acceptable_alternatives),
        "reviewed": reviewed,
    }


def fixture_paths(tmp_path: Path) -> EvalPaths:
    """An `EvalPaths` rooted at `tmp_path`: a `mini_normalized` rulebook, a
    `configs/test.toml` (judge `m-judge`, answer `m-answer`) and empty
    `datasets/`/`reports/` directories."""
    normalized_dir = mini_normalized(tmp_path)

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "test.toml").write_text(_TEST_CONFIG_TOML, encoding="utf-8")

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    return EvalPaths(
        configs_dir=configs_dir,
        datasets_dir=datasets_dir,
        reports_dir=reports_dir,
        normalized_dir=normalized_dir,
        index_dir=tmp_path / "index",
    )


async def _noop_aclose() -> None:
    return None


def fake_services(
    llm_script: Mapping[ModelRole, Sequence[str | PortError]],
    judge_script: Sequence[str | PortError],
    *,
    chunks: Sequence[RetrievedChunk] = (),
    prices: Mapping[str, ModelPrice] | None = None,
) -> tuple[ServicesFactory, FakeTracer]:
    """A `ServicesFactory` wired entirely to fakes, plus the `FakeTracer` it
    tees so a test can assert on what the graph itself recorded.

    The factory ignores `settings`/`trace_options`/`paths` (fakes need none of
    them) and tees the given `tap` alongside the `FakeTracer` returned
    here, exactly as `default_services_factory` tees the real tracer.
    """
    fake_tracer = FakeTracer()
    resolved_prices = dict(prices) if prices is not None else dict(_DEFAULT_PRICES)

    async def factory(
        config: EvalConfig,
        settings: Settings,
        trace_options: TraceOptions,
        tap: Tracer,
        paths: EvalPaths,
    ) -> EvalServices:
        tee = TeeTracer(fake_tracer, tap)
        llm = FakeLLMClient(llm_script)
        assistant, _ = make_assistant(
            llm, retriever=FakeRetriever(chunks), tracer=tee, settings=config.graph
        )
        runtime = Runtime(assistant, _noop_aclose, tracer=tee)
        judge: LLMClient = FakeLLMClient({"answer": judge_script})
        return EvalServices(
            runtime=runtime,
            judge=judge,
            prices=resolved_prices,
            aclose=_noop_aclose,
        )

    return factory, fake_tracer


class CostingLLMClient:
    """Wraps `inner`, overwriting every successful response's `cost_usd` with a
    fixed value (spec 008's `CostLLMClient` pattern, re-implemented locally so
    `evals/tests/` does not import `backend/tests/api_helpers.py`)."""

    def __init__(self, inner: LLMClient, cost: float) -> None:
        self._inner = inner
        self._cost = cost

    async def generate(self, request: LLMRequest) -> LLMResponse:
        response = await self._inner.generate(request)
        return LLMResponse(
            text=response.text,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=self._cost,
        )
