"""OpenRouter chat adapter: an `openai.AsyncOpenAI`-backed `LLMClient` (D12).

Uses the official `openai` SDK against OpenRouter's OpenAI-compatible endpoint.
Structured requests ask OpenRouter to enforce the schema (`provider.require_parameters`)
and every request asks for provider-reported cost (`usage.include`). Failures become
`PortError` without ever including the API key (D22).
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import httpx2
import openai
from openai import AsyncOpenAI
from openai.types import Embedding
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.completion_usage import CompletionUsage
from openai.types.model import Model
from openai.types.shared_params.response_format_json_schema import (
    JSONSchema,
    ResponseFormatJSONSchema,
)

from backend.ports.errors import PortError
from backend.ports.llm import LLMRequest, LLMResponse, ModelRole

OPENROUTER_BASE_URL: Final = "https://openrouter.ai/api/v1"
CHAT_TIMEOUT_S: Final = 30.0
EMBEDDINGS_TIMEOUT_S: Final = 15.0
MAX_RETRIES: Final = 1
EMBED_BATCH_SIZE: Final = 64

_REQUIRED_ROLES: Final[tuple[ModelRole, ...]] = ("router", "classifier", "answer")


def make_openrouter_client(
    api_key: str, *, timeout: float, http_client: httpx2.AsyncClient | None = None
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=timeout,
        max_retries=MAX_RETRIES,
        http_client=http_client,
    )


def _extract_cost(usage: CompletionUsage) -> float | None:
    cost = getattr(usage, "cost", None)
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        return None
    cost_usd = float(cost)
    if cost_usd < 0:
        return None
    return cost_usd


class OpenRouterLLMClient:
    """Satisfies `ports.llm.LLMClient` over OpenRouter's chat completions endpoint."""

    def __init__(self, client: AsyncOpenAI, models: Mapping[ModelRole, str]) -> None:
        missing = [role for role in _REQUIRED_ROLES if not models.get(role, "").strip()]
        if missing:
            raise ValueError(
                "invalid OpenRouterLLMClient: models must have a non-empty value "
                f"for {missing}"
            )
        self._client = client
        self._models = dict(models)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self._models[request.role]
        extra_body: dict[str, object] = {"usage": {"include": True}}
        response_format: ResponseFormat | openai.Omit = openai.omit
        if request.response_schema is not None and request.schema_name is not None:
            json_schema: JSONSchema = {
                "name": request.schema_name,
                "strict": True,
                "schema": dict(request.response_schema),
            }
            response_format = ResponseFormatJSONSchema(
                type="json_schema", json_schema=json_schema
            )
            extra_body["provider"] = {"require_parameters": True}

        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=request.system),
            ChatCompletionUserMessageParam(role="user", content=request.user),
        ]

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format=response_format,
                extra_body=extra_body,
            )
        except openai.APIStatusError as exc:
            raise PortError(
                f"openrouter chat request failed: {type(exc).__name__} "
                f"(status {exc.status_code})"
            ) from exc
        except openai.APIError as exc:
            raise PortError(
                f"openrouter chat request failed: {type(exc).__name__}"
            ) from exc

        if not response.choices:
            raise PortError("openrouter chat response had no usable choice")

        choice = response.choices[0]
        finish_reason = cast(str, choice.finish_reason)
        if finish_reason == "error":
            raise PortError("openrouter chat response had no usable choice")

        text = choice.message.content or ""
        model_name = response.model.strip() if response.model else ""

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage is not None else 0
        output_tokens = usage.completion_tokens if usage is not None else 0
        cost_usd = _extract_cost(usage) if usage is not None else None

        return LLMResponse(
            text=text,
            model=model_name or model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )


class OpenRouterEmbedder:
    """Satisfies `retrieval.embedder.Embedder` over OpenRouter's embeddings endpoint."""

    def __init__(
        self, client: AsyncOpenAI, model: str, batch_size: int = EMBED_BATCH_SIZE
    ) -> None:
        if not model.strip():
            raise ValueError("invalid OpenRouterEmbedder: model must be non-empty")
        if isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError(
                "invalid OpenRouterEmbedder: batch_size must be an int >= 1"
            )
        self._client = client
        self._model = model
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        dimensions: int | None = None
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            data = await self._embed_batch(batch)
            if len(data) != len(batch):
                raise PortError(
                    f"openrouter embeddings response has {len(data)} vectors "
                    f"for {len(batch)} inputs"
                )
            for item in sorted(data, key=lambda row: row.index):
                vector = list(item.embedding)
                if dimensions is None:
                    dimensions = len(vector)
                if dimensions == 0 or len(vector) != dimensions:
                    raise PortError(
                        "openrouter embeddings response has inconsistent dimensions"
                    )
                vectors.append(vector)
        return vectors

    async def _embed_batch(self, batch: Sequence[str]) -> list[Embedding]:
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=list(batch),
                encoding_format="float",
            )
        except openai.APIStatusError as exc:
            raise PortError(
                f"openrouter embeddings request failed: {type(exc).__name__} "
                f"(status {exc.status_code})"
            ) from exc
        except openai.APIError as exc:
            raise PortError(
                f"openrouter embeddings request failed: {type(exc).__name__}"
            ) from exc
        return response.data


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-token USD prices for one model (D8e/D10), read from OpenRouter's
    `/models` response. Both fields must be finite and `>= 0` (spec 005 D11)."""

    prompt_usd_per_token: float
    completion_usd_per_token: float

    def __post_init__(self) -> None:
        for name in ("prompt_usd_per_token", "completion_usd_per_token"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"invalid ModelPrice: {name} must be a float")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid ModelPrice: {name} must be finite and >= 0")


def _price_from_model(model: Model) -> ModelPrice | None:
    """Reads `pricing` from pydantic `model_extra` (open risk b): the openai SDK's
    `Model` type does not declare it, the same technique as `usage.cost`."""
    extra = model.model_extra or {}
    pricing = extra.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    try:
        prompt = float(cast(str, pricing["prompt"]))
        completion = float(cast(str, pricing["completion"]))
        return ModelPrice(prompt, completion)
    except (KeyError, TypeError, ValueError):
        return None


async def fetch_model_prices(
    client: AsyncOpenAI, model_ids: Collection[str]
) -> dict[str, ModelPrice]:
    """Fetches per-token prices for exactly `model_ids` from `GET /models` (D10).

    Matches ids exactly. A model id absent from the response, or present with
    missing/invalid `pricing`, raises `PortError`.
    """
    found: dict[str, ModelPrice] = {}
    wanted = set(model_ids)
    try:
        async for model in client.models.list():
            if model.id not in wanted or model.id in found:
                continue
            price = _price_from_model(model)
            if price is not None:
                found[model.id] = price
    except openai.APIStatusError as exc:
        raise PortError(
            f"openrouter models request failed: {type(exc).__name__} "
            f"(status {exc.status_code})"
        ) from exc
    except openai.APIError as exc:
        raise PortError(
            f"openrouter models request failed: {type(exc).__name__}"
        ) from exc

    for model_id in model_ids:
        if model_id not in found:
            raise PortError(f"openrouter pricing unavailable for {model_id}")

    return found
