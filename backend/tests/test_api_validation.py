"""Tests for `POST /api/chat`'s pre-stream request guards (spec 008 Testing)."""

from __future__ import annotations

import httpx2
import pytest

from backend.api.messages import (
    INVALID_REQUEST_TEXT,
    MESSAGE_TOO_LONG_TEXT,
    REQUEST_TOO_LARGE_TEXT,
    UNSUPPORTED_MEDIA_TYPE_TEXT,
)
from backend.tests.api_helpers import make_client, post_chat
from backend.tests.fakes.llm import FakeLLMClient


def _assert_rejected(
    response: httpx2.Response, status: int, code: str, text: str
) -> None:
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": text}}
    assert response.headers["cache-control"] == "no-store"


def test_wrong_content_type_415() -> None:
    llm = FakeLLMClient({})
    client, _state = make_client(llm)

    with client:
        response = client.post(
            "/api/chat",
            content=b'{"message": "hi"}',
            headers={"Content-Type": "text/plain"},
        )

    _assert_rejected(
        response, 415, "unsupported_media_type", UNSUPPORTED_MEDIA_TYPE_TEXT
    )
    assert llm.requests == []


def test_body_too_large_413() -> None:
    llm = FakeLLMClient({})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": "a" * 20000})

    _assert_rejected(response, 413, "request_too_large", REQUEST_TOO_LARGE_TEXT)
    assert llm.requests == []


@pytest.mark.parametrize(
    "body",
    [
        "not JSON",
        [],
        {},
        {"message": 5},
        {"message": "hi", "extra": 1},
        {"message": "hi", "roll": "true"},
        {"message": "hi", "modifier": 11},
        {"message": "hi", "modifier": True},
        {"message": "hi", "modifier": 1.5},
        {"message": "hi", "session_id": "XYZ"},
        {"message": "   "},
    ],
)
def test_invalid_request_422(body: object) -> None:
    llm = FakeLLMClient({})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, body)

    _assert_rejected(response, 422, "invalid_request", INVALID_REQUEST_TEXT)
    assert llm.requests == []


def test_message_too_long_422() -> None:
    llm = FakeLLMClient({})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": "a" * 501})

    _assert_rejected(response, 422, "message_too_long", MESSAGE_TOO_LONG_TEXT)
    assert llm.requests == []


def test_message_at_limit_accepted() -> None:
    llm = FakeLLMClient({"router": ["not valid json"]})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": " " + "a" * 500 + " "})

    assert response.status_code == 200


def test_non_ascii_length_counts_code_points() -> None:
    llm = FakeLLMClient({"router": ["not valid json"]})
    client, _state = make_client(llm)

    with client:
        response = post_chat(client, {"message": "é" * 500})

    assert response.status_code == 200


def test_invalid_requests_do_not_consume_rate_limit() -> None:
    llm = FakeLLMClient({"router": ["not valid json"]})
    client, _state = make_client(llm, env={"CHAT_RATE_PER_MINUTE": "1"})

    with client:
        post_chat(client, {"message": "hi", "extra": 1})
        post_chat(client, {"message": "hi", "extra": 1})
        post_chat(client, {"message": "hi", "extra": 1})
        response = post_chat(client, {"message": "hi"})

    assert response.status_code == 200
