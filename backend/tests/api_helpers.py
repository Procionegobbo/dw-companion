"""Shared test helpers for `backend/tests/test_api_*.py` (spec 008 Testing).

Not collected by pytest (no `test_` prefix). Builds a `Runtime` over spec 006 fakes
(reusing `graph_helpers.make_assistant`) behind a `create_app`-compatible
`RuntimeFactory`, so API tests never touch real adapters or the network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2
from fastapi.testclient import TestClient

from backend.adapters.metered_llm import MeteredLLMClient
from backend.api.app import CostSink, RuntimeFactory, create_app
from backend.api.limits import ClientKeyer
from backend.composition import Runtime
from backend.domain.dice import RandomSource
from backend.ports.llm import LLMClient, LLMRequest, LLMResponse
from backend.ports.retriever import Retriever
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.fakes.tracer import FakeTracer
from backend.tests.graph_helpers import (
    chunk,
    classifier_json,
    make_assistant,
    router_json,
)

_DEFAULT_CLOCK_START: float = 1_767_225_600.0  # 2026-01-01T00:00:00Z


@dataclass
class FakeClock:
    """A settable `limits.Clock` (epoch seconds), for story 003's tests."""

    start: float = _DEFAULT_CLOCK_START
    _now: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._now = self.start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


@dataclass
class RuntimeState:
    """What a test needs back from a built `Runtime` it cannot otherwise reach."""

    tracer: FakeTracer
    closed: bool = False


def runtime_factory(
    llm: LLMClient,
    *,
    retriever: Retriever | None = None,
    rng: RandomSource | None = None,
    tracer: FakeTracer | None = None,
) -> tuple[RuntimeFactory, RuntimeState]:
    resolved_tracer = tracer if tracer is not None else FakeTracer()
    resolved_retriever = retriever if retriever is not None else FakeRetriever()
    resolved_rng = rng if rng is not None else ScriptedRandom([])
    state = RuntimeState(tracer=resolved_tracer)

    def factory(sink: CostSink) -> Runtime:
        metered = MeteredLLMClient(llm, sink)
        assistant, _tracer = make_assistant(
            metered,
            retriever=resolved_retriever,
            rng=resolved_rng,
            tracer=resolved_tracer,
        )

        async def close_callback() -> None:
            state.closed = True

        return Runtime(assistant, close_callback)

    return factory, state


_RUNTIME_FACTORY_KWARGS = frozenset({"retriever", "rng", "tracer"})


def make_client(
    llm: LLMClient, *, env: Mapping[str, str] | None = None, **kw: Any
) -> tuple[TestClient, RuntimeState]:
    """`TestClient(create_app(environ=env or {}, ...))` over a fakes-backed runtime.

    Extra keyword arguments go to `runtime_factory` (`retriever`, `rng`, `tracer`) or
    to `create_app` (anything else, e.g. `turn_timeout_s`).
    """
    factory_kwargs = {k: v for k, v in kw.items() if k in _RUNTIME_FACTORY_KWARGS}
    app_kwargs = {k: v for k, v in kw.items() if k not in _RUNTIME_FACTORY_KWARGS}
    app_kwargs.setdefault("keyer", ClientKeyer(b"test-salt"))
    factory, state = runtime_factory(llm, **factory_kwargs)
    app = create_app(environ=env or {}, runtime_factory=factory, **app_kwargs)
    return TestClient(app), state


def post_chat(
    client: TestClient, body: object, *, headers: Mapping[str, str] | None = None
) -> httpx2.Response:
    """POSTs `body` to `/api/chat` with `Content-Type: application/json`.

    `body` is sent as-is when it is already `str`/`bytes` (for malformed-JSON
    cases); any other value is JSON-encoded first.
    """
    if isinstance(body, bytes):
        content: bytes = body
    elif isinstance(body, str):
        content = body.encode("utf-8")
    else:
        content = json.dumps(body).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    return client.post("/api/chat", content=content, headers=request_headers)


def parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parses the server's own SSE frames (single-line `data:`, no comments)."""
    messages: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        data: dict[str, Any] = json.loads("\n".join(data_lines)) if data_lines else {}
        messages.append((event, data))
    return messages


class SlowLLMClient:
    """Sleeps `delay_s` (real time, via `asyncio.sleep`), then answers the router."""

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s

    async def generate(self, request: LLMRequest) -> LLMResponse:
        await asyncio.sleep(self._delay_s)
        return LLMResponse(
            text=json.dumps({"intent": "rules_question", "confidence": 0.9}),
            model="fake-slow",
            input_tokens=10,
            output_tokens=5,
        )


class CostLLMClient:
    """Wraps `inner`, overwriting every response's `cost_usd` with a fixed value."""

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


__all__ = [
    "CostLLMClient",
    "FakeClock",
    "RuntimeState",
    "SlowLLMClient",
    "chunk",
    "classifier_json",
    "make_client",
    "parse_sse",
    "post_chat",
    "router_json",
    "runtime_factory",
]
