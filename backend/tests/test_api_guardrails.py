"""Tests for `POST /api/chat`'s rate limit and spend cap guards (spec 008 Testing,
guards 6-7). Every rejection case also proves no LLM call was made."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest

from backend.api.limits import seconds_until_utc_midnight
from backend.api.messages import (
    BUDGET_EXHAUSTED_TEXT,
    RATE_LIMIT_DAY_TEXT,
    RATE_LIMIT_MINUTE_TEXT,
)
from backend.ports.llm import LLMClient, LLMRequest, LLMResponse
from backend.tests.api_helpers import CostLLMClient, FakeClock, make_client, post_chat
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import chunk as fake_chunk
from backend.tests.graph_helpers import router_json


class _ScriptedCostLLMClient:
    """Wraps `inner`, assigning each successive call the next scripted `cost_usd`.

    Used where a single fixed cost (`CostLLMClient`) cannot show both halves of
    "budget rejections do not consume the rate limit": the first call must alone
    exhaust a small budget, while later calls must stay cheap enough to show the
    rate limiter (not the budget) rejecting a further request.
    """

    def __init__(self, inner: LLMClient, costs: Sequence[float]) -> None:
        self._inner = inner
        self._costs = list(costs)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        response = await self._inner.generate(request)
        cost = self._costs.pop(0)
        return LLMResponse(
            text=response.text,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=cost,
        )


def test_rate_limit_per_minute_429() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 2})
    client, _state = make_client(llm, env={"CHAT_RATE_PER_MINUTE": "2"})

    with client:
        post_chat(client, {"message": "hi"})
        post_chat(client, {"message": "hi"})
        response = post_chat(client, {"message": "hi"})

    assert response.status_code == 429
    assert response.json() == {
        "error": {"code": "rate_limited", "message": RATE_LIMIT_MINUTE_TEXT}
    }
    assert response.headers["retry-after"] == "60"
    assert len(llm.requests) == 2


def test_rate_limit_resets_after_window() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 3})
    clock = FakeClock()
    client, _state = make_client(llm, env={"CHAT_RATE_PER_MINUTE": "2"}, clock=clock)

    with client:
        post_chat(client, {"message": "hi"})
        post_chat(client, {"message": "hi"})
        rejected = post_chat(client, {"message": "hi"})
        clock.advance(61)
        allowed = post_chat(client, {"message": "hi"})

    assert rejected.status_code == 429
    assert allowed.status_code == 200
    assert len(llm.requests) == 3


def test_rate_limit_daily_429() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 2})
    clock = FakeClock()
    client, _state = make_client(
        llm,
        env={"CHAT_RATE_PER_DAY": "2", "CHAT_RATE_PER_MINUTE": "100"},
        clock=clock,
    )

    with client:
        post_chat(client, {"message": "hi"})
        post_chat(client, {"message": "hi"})
        response = post_chat(client, {"message": "hi"})

    assert response.status_code == 429
    assert response.json() == {
        "error": {"code": "rate_limited", "message": RATE_LIMIT_DAY_TEXT}
    }
    assert response.headers["retry-after"] == str(seconds_until_utc_midnight(clock()))
    assert len(llm.requests) == 2


def test_rate_limit_keyed_by_forwarded_ip() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 3})
    client, _state = make_client(
        llm, env={"CHAT_TRUSTED_PROXY_HOPS": "1", "CHAT_RATE_PER_MINUTE": "2"}
    )

    with client:
        first = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}
        )
        second = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}
        )
        third = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "9.9.9.9, 2.2.2.2"}
        )
        fourth = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "8.8.8.8, 1.1.1.1"}
        )

    assert [r.status_code for r in (first, second, third)] == [200, 200, 200]
    assert fourth.status_code == 429
    assert len(llm.requests) == 3


def test_rate_limit_ignores_forwarded_header_by_default() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 2})
    client, _state = make_client(llm, env={"CHAT_RATE_PER_MINUTE": "2"})

    with client:
        first = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "1.1.1.1"}
        )
        second = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "2.2.2.2"}
        )
        third = post_chat(
            client, {"message": "hi"}, headers={"X-Forwarded-For": "3.3.3.3"}
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_budget_exhausted_503() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, _state = make_client(llm, env={"CHAT_DAILY_BUDGET_USD": "0.01"})

    with client:
        first = post_chat(client, {"message": "hi"})
        second = post_chat(client, {"message": "hi"})

    assert first.status_code == 200
    assert second.status_code == 503
    assert second.json() == {
        "error": {"code": "budget_exhausted", "message": BUDGET_EXHAUSTED_TEXT}
    }
    assert "retry-after" in second.headers
    assert len(llm.requests) == 1


def test_budget_counts_reported_cost() -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")] * 2,
            "answer": ["Deal damage. [[moves/hack-and-slash]]"] * 2,
        }
    )
    cost_llm = CostLLMClient(llm, cost=0.004)
    retriever = FakeRetriever([fake_chunk("moves/hack-and-slash")])
    client, _state = make_client(
        cost_llm, retriever=retriever, env={"CHAT_DAILY_BUDGET_USD": "0.01"}
    )

    with client:
        first = post_chat(client, {"message": "How does hack and slash work?"})
        second = post_chat(client, {"message": "How does hack and slash work?"})
        third = post_chat(client, {"message": "How does hack and slash work?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 503
    assert len(llm.requests) == 4


def test_budget_resets_next_utc_day() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 2})
    clock = FakeClock()
    client, _state = make_client(
        llm, env={"CHAT_DAILY_BUDGET_USD": "0.01"}, clock=clock
    )

    with client:
        post_chat(client, {"message": "hi"})
        rejected = post_chat(client, {"message": "hi"})
        clock.advance(86400)
        allowed = post_chat(client, {"message": "hi"})

    assert rejected.status_code == 503
    assert allowed.status_code == 200


def test_budget_rejection_does_not_consume_rate_limit() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")] * 3})
    # The first turn alone must exhaust the 0.01 budget (matching
    # test_budget_exhausted_503's fallback-cost scenario); the next two turns must
    # stay cheap enough that the budget does not reject the third request, so that
    # rejection is clearly the rate limiter's (not the budget's) doing.
    scripted_llm = _ScriptedCostLLMClient(llm, costs=[0.01, 0.003, 0.003])
    clock = FakeClock()
    client, _state = make_client(
        scripted_llm,
        env={"CHAT_DAILY_BUDGET_USD": "0.01", "CHAT_RATE_PER_MINUTE": "2"},
        clock=clock,
    )

    with client:
        first = post_chat(client, {"message": "hi"})
        second = post_chat(client, {"message": "hi"})
        third = post_chat(client, {"message": "hi"})
        fourth = post_chat(client, {"message": "hi"})

        clock.advance(86400)

        fifth = post_chat(client, {"message": "hi"})
        sixth = post_chat(client, {"message": "hi"})
        seventh = post_chat(client, {"message": "hi"})

    assert first.status_code == 200
    assert second.status_code == 503
    assert third.status_code == 503
    assert fourth.status_code == 503
    assert fifth.status_code == 200
    assert sixth.status_code == 200
    assert seventh.status_code == 429
    assert len(llm.requests) == 3


def test_health_ok_when_budget_exhausted() -> None:
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, _state = make_client(llm, env={"CHAT_DAILY_BUDGET_USD": "0.01"})

    with client:
        post_chat(client, {"message": "hi"})
        health = client.get("/api/health")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert len(llm.requests) == 1


def test_no_ip_in_traces_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Deal damage. [[moves/hack-and-slash]]"],
        }
    )
    retriever = FakeRetriever([fake_chunk("moves/hack-and-slash")])
    client, state = make_client(
        llm,
        retriever=retriever,
        env={"CHAT_TRUSTED_PROXY_HOPS": "1", "CHAT_RATE_PER_MINUTE": "1"},
    )
    ip = "203.0.113.7"
    headers = {"X-Forwarded-For": ip}

    with caplog.at_level(logging.DEBUG, logger="backend.api"), client:
        allowed = post_chat(
            client, {"message": "How does hack and slash work?"}, headers=headers
        )
        rejected = post_chat(client, {"message": "hi"}, headers=headers)

    assert allowed.status_code == 200
    assert rejected.status_code == 429

    for node in state.tracer.nodes:
        assert ip not in node.trace_id
        assert ip not in node.session_id
        assert ip not in node.node
        for value in node.attributes.values():
            assert ip not in str(value)
    for generation in state.tracer.generations:
        assert ip not in generation.trace_id
        assert ip not in generation.session_id
        assert ip not in generation.node
    for event in state.tracer.events:
        assert ip not in event.trace_id
        assert ip not in event.session_id
        assert ip not in event.node
        assert ip not in event.name
        for value in event.attributes.values():
            assert ip not in str(value)

    for record in caplog.records:
        assert ip not in record.getMessage()
