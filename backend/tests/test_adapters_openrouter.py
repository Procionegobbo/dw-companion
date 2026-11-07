"""Tests for the OpenRouter chat adapter (spec 007 Testing).

Exercises the real `openai` SDK against an injected `httpx2.MockTransport`, so request
serialisation and response parsing are checked against the real wire format rather than
a hand-rolled fake (spec 007 D21).
"""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from backend.adapters.openrouter import (
    CHAT_TIMEOUT_S,
    EMBEDDINGS_TIMEOUT_S,
    OpenRouterEmbedder,
    OpenRouterLLMClient,
    make_openrouter_client,
)
from backend.adapters.retrieval.embedder import Embedder
from backend.ports.errors import PortError
from backend.ports.llm import LLMClient, LLMRequest, LLMResponse, ModelRole
from backend.tests.adapter_helpers import (
    RecordingHandler,
    SyncHandler,
    chat_completion_json,
    embeddings_json,
    mock_http,
)

MODELS: dict[ModelRole, str] = {
    "router": "m-router",
    "classifier": "m-classifier",
    "answer": "m-answer",
}

ROUTER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"intent": {"type": "string"}},
    "required": ["intent"],
}


def _client(handler: SyncHandler) -> OpenRouterLLMClient:
    http_client = mock_http(handler)
    openai_client = make_openrouter_client(
        "test-key", timeout=CHAT_TIMEOUT_S, http_client=http_client
    )
    return OpenRouterLLMClient(openai_client, MODELS)


def _request(
    *,
    role: ModelRole = "router",
    response_schema: dict[str, object] | None = None,
    schema_name: str | None = None,
) -> LLMRequest:
    return LLMRequest(
        role=role,
        system="You are the router.",
        user="How does Hack and Slash work?",
        max_tokens=100,
        temperature=0.0,
        response_schema=response_schema,
        schema_name=schema_name,
    )


def test_chat_request_body_for_structured_call() -> None:
    handler = RecordingHandler([(200, chat_completion_json("ok"))])
    client = _client(handler)
    request = _request(response_schema=ROUTER_SCHEMA, schema_name="router_decision")

    asyncio.run(client.generate(request))

    assert len(handler.requests) == 1
    sent = handler.requests[0]
    assert sent.url.path == "/api/v1/chat/completions"
    assert sent.headers.get("authorization") == "Bearer test-key"

    body = handler.bodies[0]
    assert body["model"] == "m-router"
    assert body["messages"] == [
        {"role": "system", "content": request.system},
        {"role": "user", "content": request.user},
    ]
    assert body["max_tokens"] == 100
    assert body["temperature"] == 0.0
    assert body["response_format"]["json_schema"]["name"] == "router_decision"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == ROUTER_SCHEMA
    assert body["provider"] == {"require_parameters": True}
    assert body["usage"] == {"include": True}


def test_chat_request_body_without_schema() -> None:
    handler = RecordingHandler([(200, chat_completion_json("ok"))])
    client = _client(handler)
    request = _request(role="answer")

    asyncio.run(client.generate(request))

    body = handler.bodies[0]
    assert body["model"] == "m-answer"
    assert "response_format" not in body
    assert "provider" not in body
    assert body["usage"] == {"include": True}


@pytest.mark.parametrize(
    ("role", "model"),
    [("router", "m-router"), ("classifier", "m-classifier"), ("answer", "m-answer")],
)
def test_model_selected_per_role(role: ModelRole, model: str) -> None:
    handler = RecordingHandler([(200, chat_completion_json("ok"))])
    client = _client(handler)

    asyncio.run(client.generate(_request(role=role)))

    assert handler.bodies[0]["model"] == model


def test_response_mapping_with_cost() -> None:
    handler = RecordingHandler(
        [
            (
                200,
                chat_completion_json(
                    "hi",
                    model="openai/test",
                    prompt_tokens=12,
                    completion_tokens=7,
                    cost=0.00042,
                ),
            )
        ]
    )
    client = _client(handler)

    response = asyncio.run(client.generate(_request()))

    assert response == LLMResponse(
        text="hi",
        model="openai/test",
        input_tokens=12,
        output_tokens=7,
        cost_usd=0.00042,
    )


def test_missing_cost_is_none() -> None:
    handler = RecordingHandler([(200, chat_completion_json("hi", cost=None))])
    client = _client(handler)

    response = asyncio.run(client.generate(_request()))

    assert response.cost_usd is None


def test_null_content_becomes_empty_text() -> None:
    handler = RecordingHandler([(200, chat_completion_json(None))])
    client = _client(handler)

    response = asyncio.run(client.generate(_request()))

    assert response.text == ""


def test_status_error_raises_port_error_without_secrets() -> None:
    handler = RecordingHandler(
        [
            (
                401,
                {
                    "error": {
                        "message": "Incorrect API key",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        ]
    )
    client = _client(handler)

    with pytest.raises(PortError) as exc_info:
        asyncio.run(client.generate(_request()))

    message = str(exc_info.value)
    assert "AuthenticationError" in message
    assert "401" in message
    assert "test-key" not in message


def test_server_error_retried_once_then_port_error() -> None:
    body = {"error": {"message": "server error", "type": "server_error"}}
    handler = RecordingHandler([(500, body), (500, body)])
    client = _client(handler)

    with pytest.raises(PortError):
        asyncio.run(client.generate(_request()))

    assert len(handler.requests) == 2


def test_timeout_raises_port_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out")

    client = _client(handler)

    with pytest.raises(PortError, match="APITimeoutError"):
        asyncio.run(client.generate(_request()))


def test_no_choices_raises_port_error() -> None:
    handler = RecordingHandler(
        [
            (
                200,
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "openai/test",
                    "choices": [],
                },
            )
        ]
    )
    client = _client(handler)

    with pytest.raises(PortError):
        asyncio.run(client.generate(_request()))


def test_missing_model_role_rejected() -> None:
    http_client = mock_http(RecordingHandler([]))
    openai_client = make_openrouter_client(
        "test-key", timeout=CHAT_TIMEOUT_S, http_client=http_client
    )

    with pytest.raises(ValueError, match="classifier"):
        OpenRouterLLMClient(openai_client, {"router": "m-router", "answer": "m-answer"})


def _embedder(handler: SyncHandler, batch_size: int = 64) -> OpenRouterEmbedder:
    http_client = mock_http(handler)
    openai_client = make_openrouter_client(
        "test-key", timeout=EMBEDDINGS_TIMEOUT_S, http_client=http_client
    )
    return OpenRouterEmbedder(openai_client, "m-embed", batch_size=batch_size)


def test_embedder_batches_in_order() -> None:
    last_batch = embeddings_json([[128.0], [129.0]])
    last_batch["data"] = list(reversed(list(last_batch["data"])))  # type: ignore[arg-type]
    handler = RecordingHandler(
        [
            (200, embeddings_json([[float(i)] for i in range(64)])),
            (200, embeddings_json([[float(i)] for i in range(64, 128)])),
            (200, last_batch),
        ]
    )
    embedder = _embedder(handler)

    vectors = asyncio.run(embedder.embed([f"text-{i}" for i in range(130)]))

    assert len(handler.requests) == 3
    assert [len(body["input"]) for body in handler.bodies] == [64, 64, 2]
    for body in handler.bodies:
        assert body["encoding_format"] == "float"
        assert body["model"] == "m-embed"
    assert vectors == [[float(i)] for i in range(130)]


def test_embedder_count_mismatch_raises() -> None:
    handler = RecordingHandler([(200, embeddings_json([[1.0, 2.0]]))])
    embedder = _embedder(handler)

    with pytest.raises(PortError):
        asyncio.run(embedder.embed(["a", "b"]))


def test_embedder_empty_input_no_request() -> None:
    handler = RecordingHandler([])
    embedder = _embedder(handler)

    result = asyncio.run(embedder.embed([]))

    assert result == []
    assert handler.requests == []


def test_adapters_satisfy_protocols() -> None:
    http_client = mock_http(RecordingHandler([]))
    openai_client = make_openrouter_client(
        "test-key", timeout=CHAT_TIMEOUT_S, http_client=http_client
    )
    llm: LLMClient = OpenRouterLLMClient(openai_client, MODELS)
    embedder: Embedder = OpenRouterEmbedder(openai_client, "m-embed")
    assert isinstance(llm, OpenRouterLLMClient)
    assert isinstance(embedder, OpenRouterEmbedder)
