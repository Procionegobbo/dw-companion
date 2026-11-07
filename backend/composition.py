"""The composition root: reads environment variables and wires the real adapters
into the spec 006 graph (D19).

The only module, besides `backend/chat.py`, that imports both `backend.adapters.*`
and `backend.graph.*`. Env is read only here, in `Settings.from_env`; adapters never
read `os.environ` themselves.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import httpx2
from opentelemetry.sdk.trace.export import SpanExporter

from backend.adapters.json_rulebook import JsonRulebookRepository
from backend.adapters.langfuse_tracer import make_langfuse_tracer
from backend.adapters.null_tracer import NullTracer
from backend.adapters.openrouter import (
    CHAT_TIMEOUT_S,
    EMBEDDINGS_TIMEOUT_S,
    OpenRouterEmbedder,
    OpenRouterLLMClient,
    make_openrouter_client,
)
from backend.adapters.retrieval.hybrid import HybridRetriever
from backend.adapters.retrieval.index import load_index
from backend.domain.dice import RandomSource
from backend.graph.builder import Assistant, build_assistant
from backend.graph.deps import GraphDeps

logger = logging.getLogger("backend.composition")

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_INDEX_DIR: Final = REPO_ROOT / "data" / "index"
DEFAULT_NORMALIZED_DIR: Final = REPO_ROOT / "data" / "normalized"

_DEFAULT_LANGFUSE_BASE_URL: Final = "https://cloud.langfuse.com"

ENV_VARS: Final[tuple[str, ...]] = (
    "OPENROUTER_API_KEY",
    "MODEL_ROUTER",
    "MODEL_CLASSIFIER",
    "MODEL_ANSWER",
    "MODEL_EMBEDDINGS",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
)


class ConfigError(Exception):
    """Invalid or missing configuration, listing every problem at once (D23)."""


@dataclass(frozen=True, slots=True)
class LangfuseSettings:
    public_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    base_url: str


@dataclass(frozen=True, slots=True)
class Settings:
    openrouter_api_key: str = field(repr=False)
    model_router: str
    model_classifier: str
    model_answer: str
    model_embeddings: str
    langfuse: LangfuseSettings | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings:
        def value(name: str) -> str:
            return environ.get(name, "").strip()

        problems: list[str] = []

        openrouter_api_key = value("OPENROUTER_API_KEY")
        if not openrouter_api_key:
            problems.append("OPENROUTER_API_KEY is required")
        model_router = value("MODEL_ROUTER")
        if not model_router:
            problems.append("MODEL_ROUTER is required")
        model_classifier = value("MODEL_CLASSIFIER")
        if not model_classifier:
            problems.append("MODEL_CLASSIFIER is required")
        model_answer = value("MODEL_ANSWER")
        if not model_answer:
            problems.append("MODEL_ANSWER is required")
        model_embeddings = value("MODEL_EMBEDDINGS")
        if not model_embeddings:
            problems.append("MODEL_EMBEDDINGS is required")

        public_key = value("LANGFUSE_PUBLIC_KEY")
        secret_key = value("LANGFUSE_SECRET_KEY")
        base_url = value("LANGFUSE_BASE_URL")

        if bool(public_key) != bool(secret_key):
            problems.append(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must both be set or "
                "both be empty"
            )
        resolved_base_url = base_url or _DEFAULT_LANGFUSE_BASE_URL
        if base_url and not (
            resolved_base_url.startswith("https://")
            or resolved_base_url.startswith("http://")
        ):
            problems.append("LANGFUSE_BASE_URL must start with https:// or http://")

        if problems:
            raise ConfigError("invalid configuration: " + "; ".join(problems))

        langfuse = (
            LangfuseSettings(
                public_key=public_key, secret_key=secret_key, base_url=resolved_base_url
            )
            if public_key and secret_key
            else None
        )

        return cls(
            openrouter_api_key=openrouter_api_key,
            model_router=model_router,
            model_classifier=model_classifier,
            model_answer=model_answer,
            model_embeddings=model_embeddings,
            langfuse=langfuse,
        )


class Runtime:
    """A built assistant plus the teardown it needs (D19).

    `close_callback` is a plain public attribute, not frozen, so tests may pass any
    coroutine function. `aclose` is idempotent: a second call is a no-op.
    """

    def __init__(
        self, assistant: Assistant, close_callback: Callable[[], Awaitable[None]]
    ) -> None:
        self.assistant = assistant
        self.close_callback = close_callback
        self._closed = False

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.close_callback()


def build_runtime(
    settings: Settings,
    *,
    index_dir: Path = DEFAULT_INDEX_DIR,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    http_client: httpx2.AsyncClient | None = None,
    span_exporter: SpanExporter | None = None,
    rng: RandomSource | None = None,
) -> Runtime:
    index = load_index(index_dir)
    if index.manifest.embedding_model != settings.model_embeddings:
        raise ConfigError(
            f"index was built with '{index.manifest.embedding_model}' but "
            f"MODEL_EMBEDDINGS is '{settings.model_embeddings}'; rebuild the index "
            "(python -m backend.adapters.retrieval.build)"
        )

    rulebook = JsonRulebookRepository.from_dir(normalized_dir)

    chat_client = make_openrouter_client(
        settings.openrouter_api_key, timeout=CHAT_TIMEOUT_S, http_client=http_client
    )
    embeddings_client = make_openrouter_client(
        settings.openrouter_api_key,
        timeout=EMBEDDINGS_TIMEOUT_S,
        http_client=http_client,
    )

    llm = OpenRouterLLMClient(
        chat_client,
        {
            "router": settings.model_router,
            "classifier": settings.model_classifier,
            "answer": settings.model_answer,
        },
    )
    retriever = HybridRetriever(
        index, OpenRouterEmbedder(embeddings_client, settings.model_embeddings)
    )

    if settings.langfuse is not None:
        tracer = make_langfuse_tracer(
            settings.langfuse.public_key,
            settings.langfuse.secret_key,
            settings.langfuse.base_url,
            span_exporter=span_exporter,
        )
    else:
        tracer = NullTracer()
        logger.warning("Langfuse keys not set; tracing disabled")

    assistant = build_assistant(
        GraphDeps(
            llm=llm,
            retriever=retriever,
            tracer=tracer,
            rulebook=rulebook,
            rng=rng if rng is not None else random.Random(),
        )
    )

    async def close_callback() -> None:
        await chat_client.close()
        await embeddings_client.close()
        tracer.close()

    return Runtime(assistant, close_callback)
