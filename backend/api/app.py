"""The FastAPI app: `POST /api/chat` (SSE) and `GET /api/health` (spec 008 API
Behaviour, Lifespan and wiring).

`create_app` reads `ApiSettings` eagerly, so a bad `CHAT_*` value fails before the
app is even built (D14). The `Runtime` itself is built lazily, in the lifespan, so a
bad `OPENROUTER_API_KEY` fails fast at startup rather than on the first request.
Guards run in D8 order: content type, body size, schema, message length, the global
spend cap, then the per-client rate limit (which records the request). Each guard
raises `ApiError`, turned into the shared JSON error body by `handle_api_error`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.staticfiles import StaticFiles

from backend.api.limits import (
    ClientKeyer,
    Clock,
    RateLimiter,
    SpendLedger,
    client_ip,
    seconds_until_utc_midnight,
)
from backend.api.messages import (
    BUDGET_EXHAUSTED_TEXT,
    INVALID_REQUEST_TEXT,
    MESSAGE_TOO_LONG_TEXT,
    RATE_LIMIT_DAY_TEXT,
    RATE_LIMIT_MINUTE_TEXT,
    REQUEST_TOO_LARGE_TEXT,
    TIMEOUT_TEXT,
    UNSUPPORTED_MEDIA_TYPE_TEXT,
)
from backend.api.schemas import ApiError, ChatRequest, reply_payload
from backend.api.settings import (
    MAX_BODY_BYTES,
    MAX_MESSAGE_CHARS,
    TURN_TIMEOUT_S,
    ApiSettings,
)
from backend.api.sse import sse_event
from backend.composition import Runtime, Settings, build_runtime
from backend.graph.replies import ERROR_TEXT
from backend.graph.state import NodeCompleted, TurnInput

logger = logging.getLogger("backend.api")

CostSink = Callable[[float], None]
RuntimeFactory = Callable[[CostSink], Runtime]


def _default_runtime_factory(environ: Mapping[str, str]) -> RuntimeFactory:
    def factory(sink: CostSink) -> Runtime:
        settings = Settings.from_env(environ)
        return build_runtime(settings, on_llm_cost=sink)

    return factory


def create_app(
    *,
    environ: Mapping[str, str] | None = None,
    runtime_factory: RuntimeFactory | None = None,
    clock: Clock = time.time,
    keyer: ClientKeyer | None = None,
    turn_timeout_s: float = TURN_TIMEOUT_S,
) -> FastAPI:
    resolved_environ = environ if environ is not None else os.environ
    api_settings = ApiSettings.from_env(resolved_environ)  # fail fast on bad CHAT_*

    resolved_factory = (
        runtime_factory
        if runtime_factory is not None
        else _default_runtime_factory(resolved_environ)
    )

    ledger = SpendLedger(api_settings.daily_budget_usd, clock)
    limiter = RateLimiter(
        api_settings.rate_per_minute, api_settings.rate_per_day, clock
    )
    resolved_keyer = keyer if keyer is not None else ClientKeyer()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        runtime = resolved_factory(ledger.record)
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        logger.info("chat request rejected: %s", exc.code)
        headers = {"Cache-Control": "no-store"}
        if exc.retry_after_s is not None:
            headers["Retry-After"] = str(exc.retry_after_s)
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers=headers,
        )

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})

    @app.post("/api/chat")
    async def chat(request: Request) -> Response:
        content_type = request.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise ApiError(415, "unsupported_media_type", UNSUPPORTED_MEDIA_TYPE_TEXT)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = False
            if too_large:
                raise ApiError(413, "request_too_large", REQUEST_TOO_LARGE_TEXT)

        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > MAX_BODY_BYTES:
                raise ApiError(413, "request_too_large", REQUEST_TOO_LARGE_TEXT)

        try:
            chat_request = ChatRequest.model_validate_json(bytes(body))
        except ValidationError as exc:
            raise ApiError(422, "invalid_request", INVALID_REQUEST_TEXT) from exc

        message = chat_request.message.strip()
        if not message:
            raise ApiError(422, "invalid_request", INVALID_REQUEST_TEXT)
        if len(message) > MAX_MESSAGE_CHARS:
            raise ApiError(422, "message_too_long", MESSAGE_TOO_LONG_TEXT)

        if ledger.exhausted():
            raise ApiError(
                503,
                "budget_exhausted",
                BUDGET_EXHAUSTED_TEXT,
                retry_after_s=seconds_until_utc_midnight(clock()),
            )

        peer_host = request.client.host if request.client else None
        ip = client_ip(request.headers, peer_host, api_settings.trusted_proxy_hops)
        decision = limiter.check(resolved_keyer.key(ip))
        if not decision.allowed:
            rate_limit_text = (
                RATE_LIMIT_DAY_TEXT
                if decision.scope == "day"
                else RATE_LIMIT_MINUTE_TEXT
            )
            raise ApiError(
                429,
                "rate_limited",
                rate_limit_text,
                retry_after_s=decision.retry_after_s,
            )

        turn_input = TurnInput(
            message=message,
            session_id=chat_request.session_id or uuid4().hex,
            trace_id=uuid4().hex,
            roll_requested=chat_request.roll,
            modifier=chat_request.modifier,
        )

        runtime = cast(Runtime, request.app.state.runtime)

        async def gen() -> AsyncIterator[bytes]:
            try:
                async with asyncio.timeout(turn_timeout_s):
                    async for ev in runtime.assistant.stream(turn_input):
                        if isinstance(ev, NodeCompleted):
                            yield sse_event("status", {"step": ev.node})
                        else:
                            yield sse_event(
                                "reply", reply_payload(ev, turn_input.trace_id)
                            )
            except TimeoutError:
                logger.warning("chat turn timed out trace_id=%s", turn_input.trace_id)
                yield sse_event("error", {"code": "timeout", "message": TIMEOUT_TEXT})
            except Exception as exc:  # mapped to one error event, never re-raised (D13)
                logger.error(
                    "chat turn failed: %s trace_id=%s",
                    type(exc).__name__,
                    turn_input.trace_id,
                    exc_info=True,
                )
                yield sse_event(
                    "error", {"code": "internal_error", "message": ERROR_TEXT}
                )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    if api_settings.site_dir is not None:
        app.mount(
            "/", StaticFiles(directory=api_settings.site_dir, html=True), name="site"
        )

    return app
