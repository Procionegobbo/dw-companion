"""Tests for `MeteredLLMClient` (spec 008 Testing)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from backend.adapters.metered_llm import FALLBACK_CALL_COST_USD, MeteredLLMClient
from backend.ports.errors import PortError
from backend.ports.llm import LLMClient, LLMRequest, LLMResponse


def _request() -> LLMRequest:
    return LLMRequest(
        role="router", system="s", user="u", max_tokens=10, temperature=0.0
    )


class _FakeInner:
    """Per-role-agnostic FIFO queue of scripted responses or `PortError`s."""

    def __init__(self, responses: list[LLMResponse | PortError]) -> None:
        self._queue = list(responses)
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        next_value = self._queue.pop(0)
        if isinstance(next_value, PortError):
            raise next_value
        return next_value


def test_records_provider_cost() -> None:
    inner = _FakeInner(
        [
            LLMResponse(
                text="t", model="m", input_tokens=1, output_tokens=1, cost_usd=0.002
            )
        ]
    )
    costs: list[float] = []
    client = MeteredLLMClient(inner, costs.append)

    response = asyncio.run(client.generate(_request()))

    assert costs == [0.002]
    assert response.text == "t"


def test_missing_cost_counts_fallback_and_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    inner = _FakeInner(
        [
            LLMResponse(text="a", model="m", input_tokens=1, output_tokens=1),
            LLMResponse(text="b", model="m", input_tokens=1, output_tokens=1),
        ]
    )
    costs: list[float] = []
    client = MeteredLLMClient(inner, costs.append)

    with caplog.at_level(logging.WARNING, logger="backend.adapters.metered_llm"):
        asyncio.run(client.generate(_request()))
        asyncio.run(client.generate(_request()))

    assert costs == [FALLBACK_CALL_COST_USD, FALLBACK_CALL_COST_USD]
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.name == "backend.adapters.metered_llm"
    ]
    assert len(warnings) == 1


def test_port_error_records_nothing() -> None:
    inner = _FakeInner([PortError("down")])
    costs: list[float] = []
    client = MeteredLLMClient(inner, costs.append)

    with pytest.raises(PortError):
        asyncio.run(client.generate(_request()))

    assert costs == []


def test_request_passed_through_unchanged() -> None:
    response = LLMResponse(
        text="t", model="m", input_tokens=1, output_tokens=1, cost_usd=0.0001
    )
    inner = _FakeInner([response])
    client = MeteredLLMClient(inner, lambda _cost: None)
    request = _request()

    result = asyncio.run(client.generate(request))

    assert result is response
    assert inner.requests == [request]


def test_satisfies_llm_client_protocol() -> None:
    inner = _FakeInner([])
    client: LLMClient = MeteredLLMClient(inner, lambda _cost: None)
    assert isinstance(client, MeteredLLMClient)
