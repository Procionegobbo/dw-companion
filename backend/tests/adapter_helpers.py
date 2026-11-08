"""Shared test helpers for the adapter tests (spec 007 Testing; spec 009 D8/D10 adds
`memory_exporter` and `models_json`).

HTTP parts (`mock_http`, `chat_completion_json`, `RecordingHandler`), `mini_normalized`
(the small committed-data-shaped fixture used by the chunking and retrieval tests),
`memory_tracer` (an in-memory-exported `LangfuseTracer`) and the two scripted embedders
used by `test_adapters_hybrid.py`. Not collected by pytest (no `test_` prefix).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from backend.adapters.langfuse_tracer import LangfuseTracer, make_langfuse_tracer
from backend.adapters.retrieval.bm25 import tokenize
from backend.tests.domain_helpers import (
    DEFY_DANGER,
    DISCERN_REALITIES,
    HACK_AND_SLASH,
    LAST_BREATH,
    MAKE_CAMP,
    VOLLEY,
)
from backend.tests.fakes.embedder import FakeEmbedder

SyncHandler = Callable[[httpx2.Request], httpx2.Response]


def mock_http(handler: SyncHandler) -> httpx2.AsyncClient:
    """An `httpx2.AsyncClient` routed through `handler` instead of the network."""
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def chat_completion_json(
    content: str | None,
    model: str = "openai/test",
    prompt_tokens: int = 12,
    completion_tokens: int = 7,
    cost: float | None = 0.00042,
) -> dict[str, object]:
    """An OpenRouter-shaped chat completion response body."""
    usage: dict[str, object] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def embeddings_json(
    vectors: Sequence[Sequence[float]], model: str = "openai/test-embed"
) -> dict[str, object]:
    """An OpenRouter-shaped embeddings response body, `data` in index order."""
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": list(vector)}
            for i, vector in enumerate(vectors)
        ],
        "model": model,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


class RecordingHandler:
    """Stores each request and its parsed JSON body, replying from a response queue."""

    def __init__(self, responses: Sequence[tuple[int, object]]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx2.Request] = []
        self.bodies: list[Any] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.bodies.append(json.loads(request.content))
        if not self._responses:
            raise AssertionError(
                "RecordingHandler exhausted: no more scripted responses"
            )
        status, body = self._responses.pop(0)
        return httpx2.Response(status, json=body)


_MOVE_FIXTURES: tuple[dict[str, object], ...] = (
    HACK_AND_SLASH,
    DEFY_DANGER,
    VOLLEY,
    DISCERN_REALITIES,
    LAST_BREATH,
    MAKE_CAMP,
)


def _section(
    section_id: str,
    chapter: str,
    title: str,
    slug: str,
    parent_id: str | None,
    order: int,
    text_markdown: str,
) -> dict[str, object]:
    return {
        "id": section_id,
        "chapter": chapter,
        "title": title,
        "slug": slug,
        "parent_id": parent_id,
        "order": order,
        "text_markdown": text_markdown,
    }


def mini_normalized(tmp_path: Path) -> Path:
    """Writes a small `sections.json`/`moves.json` pair (spec 007 Testing) and returns
    the directory holding them."""
    big_section_text = "\n\n".join(f"Block {i}: " + "x" * 1500 for i in range(1, 9))

    sections: list[dict[str, object]] = [
        _section(
            "moves",
            "moves",
            "Moves",
            "moves",
            None,
            0,
            "Moves are rules that tell you when they trigger.",
        ),
    ]
    for position, move in enumerate(_MOVE_FIXTURES, start=1):
        move_id = move["id"]
        assert isinstance(move_id, str)
        sections.append(
            _section(
                f"moves/{move_id}",
                "moves",
                str(move["name"]),
                move_id,
                "moves",
                position,
                str(move["body_markdown"]),
            )
        )
    sections.extend(
        [
            _section("moves/empty", "moves", "Empty", "empty", "moves", 7, ""),
            _section(
                "gm",
                "gm",
                "The GM",
                "gm",
                None,
                8,
                "The GM's agenda and principles.",
            ),
            _section(
                "gm/big-section",
                "gm",
                "Big Section",
                "big-section",
                "gm",
                9,
                big_section_text,
            ),
            _section(
                "gm/huge-block",
                "gm",
                "Huge Block",
                "huge-block",
                "gm",
                10,
                "y" * 7000,
            ),
            _section(
                "thanks",
                "thanks",
                "Thanks",
                "thanks",
                None,
                11,
                "Backer One, Backer Two.",
            ),
        ]
    )

    moves = [dict(move) for move in _MOVE_FIXTURES]

    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    (normalized_dir / "sections.json").write_text(
        json.dumps(sections, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (normalized_dir / "moves.json").write_text(
        json.dumps(moves, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return normalized_dir


class VectorStubEmbedder:
    """An `Embedder` returning scripted vectors for known texts, a hashed bag-of-words
    fallback (dimension-matched to the index) for everything else.

    Used by `test_bm25_rescues_exact_term` to force the vector ranking to favour a
    specific chunk (by mapping the query text to that chunk's stored row), while
    letting BM25 rank on the actual query terms.
    """

    def __init__(
        self, index_dir: Path, query_vectors: Mapping[str, Sequence[float]]
    ) -> None:
        manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        self._query_vectors = query_vectors
        self._fallback = FakeEmbedder(dim=int(manifest["dimensions"]))

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            if text in self._query_vectors:
                results.append(list(self._query_vectors[text]))
            else:
                results.append((await self._fallback.embed([text]))[0])
        return results


class ScriptedEmbedder:
    """An `Embedder` returning exactly the mapped vector for each known text, and
    raising `AssertionError` for anything else (a hand-built, fully controlled
    corpus, e.g. `test_rrf_order`'s two-chunk `LoadedIndex`)."""

    def __init__(self, vectors: Mapping[str, Sequence[float]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            if text not in self._vectors:
                raise AssertionError(f"ScriptedEmbedder: unmapped text {text!r}")
            results.append(list(self._vectors[text]))
        return results


def memory_exporter() -> InMemorySpanExporter:
    """A fresh in-memory span exporter, for tests that need to pass `trace_name`,
    `static_metadata` or `static_tags` to `make_langfuse_tracer` directly (spec 009
    D8c), which `memory_tracer()` does not expose."""
    return InMemorySpanExporter()


def models_json(prices: Mapping[str, tuple[str, str]]) -> dict[str, object]:
    """An OpenRouter-shaped `GET /models` response body (spec 009 D10), with
    string `pricing.prompt`/`pricing.completion` per model id."""
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "openrouter",
                "pricing": {"prompt": prompt, "completion": completion},
            }
            for model_id, (prompt, completion) in prices.items()
        ],
    }


def fake_embedding_vector(text: str, dim: int = 64) -> list[float]:
    """Mirrors `FakeEmbedder`'s hashed bag-of-words algorithm, so a mocked
    `/embeddings` endpoint can return vectors matching a `FakeEmbedder`-built
    index (spec 009 D16's CLI wiring test; same technique as `VectorStubEmbedder`
    above, exposed directly here so callers outside `backend/` - which may not
    import `httpx2` themselves - can still build a consistent mock transport via
    `mock_openrouter_transport`)."""
    vector = [0.0] * dim
    for token in tokenize(text):
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        vector[index % dim] += 1.0
    if all(value == 0.0 for value in vector):
        vector[0] = 1.0
    return vector


def mock_openrouter_transport(
    *,
    prices: Mapping[str, tuple[str, str]],
    chat_response: Callable[[str, Mapping[str, object]], str],
    embedding_dim: int = 64,
) -> tuple[SyncHandler, list[dict[str, object]]]:
    """A `mock_http` handler answering OpenRouter's `GET /models`, `POST
    /embeddings` and `POST /chat/completions` (spec 009 D16's CLI wiring test).
    `/models` replies from `prices` (`models_json`); `/embeddings` replies with
    `fake_embedding_vector`s, matching a `FakeEmbedder`-built index; `/chat/
    completions` replies with `chat_response(model, body)`'s text. Returns the
    handler and the list of every chat completion request body, in order - so
    a caller that must not import `httpx2` directly (evals/ never does, D8)
    can still build and inspect a full mock transport."""
    requests: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/models"):
            return httpx2.Response(200, json=models_json(prices))
        if request.url.path.endswith("/embeddings"):
            body = json.loads(request.content)
            vectors = [
                fake_embedding_vector(text, embedding_dim) for text in body["input"]
            ]
            return httpx2.Response(
                200, json=embeddings_json(vectors, model=body["model"])
            )
        body = json.loads(request.content)
        requests.append(body)
        model = body["model"]
        content = chat_response(model, body)
        return httpx2.Response(200, json=chat_completion_json(content, model=model))

    return handler, requests


def memory_tracer() -> tuple[LangfuseTracer, InMemorySpanExporter]:
    """A `LangfuseTracer` exporting to an `InMemorySpanExporter` (spec 007 D21/open
    risk b: a unique public key per test client, since Langfuse keeps one resource
    manager per public key)."""
    exporter = InMemorySpanExporter()
    tracer = make_langfuse_tracer(
        f"pk-test-{uuid4().hex}",
        "sk-test",
        "https://langfuse.invalid",
        span_exporter=exporter,
    )
    return tracer, exporter
