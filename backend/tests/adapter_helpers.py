"""Shared test helpers for the adapter tests (spec 007 Testing).

HTTP parts (`mock_http`, `chat_completion_json`, `RecordingHandler`), `mini_normalized`
(the small committed-data-shaped fixture used by the chunking and retrieval tests),
`memory_tracer` (an in-memory-exported `LangfuseTracer`) and the two scripted embedders
used by `test_adapters_hybrid.py`. Not collected by pytest (no `test_` prefix).
"""

from __future__ import annotations

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
