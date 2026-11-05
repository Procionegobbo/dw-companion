# 008 - API and chat widget

**Status:** spec — ready for story-creator.
**Depends on:** 001 (toolchain, `backend/api/` package, `.env.example` rule, CI), 003 (`astro-feature-builder` must exist before the frontend stories; a pipeline concern only), 004 (Astro site, URL contract D1, `urls.ts`, `format.ts`, `SiteHeader`, Vitest suites), 005 (`Roll`, `Outcome`, `Outcomes`, `Band`, `MIN_MODIFIER`/`MAX_MODIFIER`), 006 (`Assistant`, `TurnInput`, `TurnResult`, `Reply`, `MoveCard`, `Citation`, `[[section_id]]` markers, `ERROR_TEXT`, fakes, socket guard), 007 (`build_runtime`, `Runtime`, `Settings`, `ConfigError`, `LLMResponse.cost_usd`).
**Reference:** `HANDOFF_dw-companion.md` sections 4.5, 7, 8, 10 (milestone 7), 12.

## Feature Name & Description

**Chat API and chat widget.** A FastAPI app in `backend/api/` exposes `POST /api/chat`, which runs one assistant turn and streams progress and the final structured reply as Server-Sent Events, and `GET /api/health`. Before any LLM call, the API enforces a body size limit, strict request validation, a 500-character message limit, a global daily spend cap and per-IP rate limits. A chat widget on a new `/assistant/` page of the Astro site sends messages to the API on the same origin. It shows progress while the turn runs, then renders the answer with citation links to rules pages and a move card (name, roll stat, outcome bands, dice result). This is milestone 7: the assistant becomes usable from the browser, with guardrails in place.

**Current state.** Nothing is implemented; specs 001–007 are approved but not built. Paths marked "(new in 00N)" come from those specs and do not exist on disk yet. Spec 006 gives `Assistant.run(TurnInput) -> TurnResult` with no streaming hook except an opaque `compiled` property. Spec 007 gives `build_runtime(settings) -> Runtime` and reports `cost_usd` per LLM call, but nothing aggregates it. The site has no client-side JavaScript and no page for the assistant.

**In scope.**
- Backend: `Assistant.stream` (node-level progress, additive), an LLM cost-metering wrapper and an `on_llm_cost` hook in `build_runtime`, the FastAPI app (`/api/chat` over SSE, `/api/health`), request validation, in-memory rate limiter and spend ledger, env settings, the dependencies `fastapi` and `uvicorn`, and a shared reply-payload fixture.
- Frontend: SSE parser, protocol schemas, chat client, DOM rendering, widget controller, `ChatWidget.astro`, the `/assistant/` page, a header link, a dev proxy for `/api`, and `happy-dom` for DOM tests.
- Two ADRs, an architecture section, README subsection, `.env.example` keys.

**Out of scope.**
- Token-level LLM streaming (D2), conversation memory (spec 006 D15).
- Rate-limit and budget state shared across instances or restarts (D9).
- Serving the static site from FastAPI, the Dockerfile, Cloud Run settings, Secret Manager, billing alerts (spec 011).
- Evals (spec 009), README polish (spec 012).

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **SSE protocol: three event types on one `POST /api/chat` stream.** `status` `{"step": "<node>"}` is sent after each graph node completes. `reply` `{trace_id, kind, text, citations, move}` is sent once, as the last event of a successful turn. `error` `{"code", "message"}` is sent once, as the last event, when the turn fails after streaming started. Each frame is `event: <name>\ndata: <single-line JSON>\n\n`. No `id`/`retry` fields, no keep-alive comments. Clients must ignore unknown event names (forward-compatible). Exact schemas are in *Data Model*. | Handoff 4 says "POST /api/chat (SSE streaming)". Named events give the widget a clear switch, and one terminal event makes "stream ended without a result" detectable. Turns take seconds and `status` events flow throughout, so keep-alive pings add nothing. |
| D2 | **No partial-token (`delta`) event in this spec. The reply text arrives whole in `reply`.** "Streams the answer" means live progress (`status`) followed by the validated answer on the same stream. **Owner review item #1.** | Spec 006's citation validator needs the complete LLM answer before any of it can be shown. Raw tokens would display `[[id]]` citations that the validator then strips, which would undermine the project's anti-hallucination signal (handoff 4.4). Spec 006 has no token streaming in the `LLMClient` port, and adding it changes every adapter and fake. Because clients ignore unknown events, a later `delta` event can be added without breaking the widget (*Future Considerations*). |
| D3 | **Rejections before streaming are plain HTTP JSON responses, not SSE events.** Status and `error.code`: 415 `unsupported_media_type`, 413 `request_too_large`, 422 `invalid_request` / `message_too_long`, 503 `budget_exhausted`, 429 `rate_limited`. The body is always `{"error": {"code", "message"}}`, with server-authored copy. 429 and 503 carry `Retry-After`. | Every guardrail decision is made before any LLM call (handoff 7), so no stream needs to be opened. Status codes are visible to curl, Cloud Run metrics and tests without parsing a stream. 503 (not 429) for the budget distinguishes "everyone is blocked" from "you are blocked". |
| D4 | **Node-level progress comes from a new `Assistant.stream(turn)`** in `backend/graph/builder.py`. It is an async iterator yielding `NodeCompleted(node)` per executed node, then exactly one `TurnResult`. It uses LangGraph `astream(..., stream_mode=["updates", "values"])`. `Assistant.run` is unchanged. | Spec 006 D1 picked LangGraph partly for "node-level streaming, which spec 008's SSE needs", and D2 confines LangGraph to `builder.py`. So the API gets streaming through our own type and never touches the opaque `compiled` property. Additive. |
| D5 | **FastAPI with Starlette `StreamingResponse` and a 10-line SSE frame formatter.** FastAPI's native `EventSourceResponse` (present in 0.162) is not used. New runtime dependencies are `fastapi` and `uvicorn`. PR lines: *"fastapi: the API framework named in the project brief (handoff 4.1); typed request models and an ASGI app Cloud Run can serve."* *"uvicorn: the standard ASGI server to run the app locally and in the container (spec 011)."* `httpx2`, already installed by `openai` (spec 007), backs `starlette.testclient`, so no new dev dependency is needed. | A route that returns either a JSON error (D3) or a stream needs a plain function returning a `Response`. The native SSE route has to be a generator, which pushes the guards into exception-raising dependencies. An explicit formatter is trivially unit-testable and does not depend on a recent FastAPI API. Verified 2026-11-05: fastapi 0.162.0, starlette 1.10.0 (its `testclient` imports `httpx2`), uvicorn 0.54.0. |
| D6 | **The widget talks to `fetch("/api/chat")` (relative, same origin) and reads `response.body` as a stream with its own SSE parser.** It does not use `EventSource`. In development, the Astro dev server proxies `/api` to `http://127.0.0.1:8000` (Vite `server.proxy`). In production, spec 011's single container serves both the site and the API (planned, not built). The API sends no CORS headers. | `EventSource` only does GET with no body, and its automatic reconnection would re-send (and re-bill) a turn. A relative path needs no build-time API URL and no CORS. The dev proxy reproduces the production same-origin setup locally. |
| D7 | **Request body:** `{"message": str, "roll": bool = false, "modifier": int \| null = null, "session_id": str \| null = null}`. It is validated strictly: no extra keys, no type coercion. `message` is stripped; it must then be non-empty and at most `MAX_MESSAGE_CHARS = 500` characters (Python `len`, code points). `modifier` is in −10…10 (spec 005). `session_id` matches `^[0-9a-f]{32}$`, and the server generates `uuid4().hex` when it is absent. `trace_id` is always generated by the server (`uuid4().hex`, spec 007 D15). | Handoff 7: max input length, checked before any LLM call. 500 characters fits a rules question or a described action with room to spare, while bounding prompt cost. The widget generates one random session id per page load, so Langfuse groups a visitor's turns (handoff 7: random session ID) without cookies or storage. The textarea's `maxlength` counts UTF-16 units, which is never more permissive than the server's code-point count. |
| D8 | **Guard order for `POST /api/chat`:** content type → body size (`MAX_BODY_BYTES = 16384`, read incrementally) → JSON and schema → message rules → spend cap → rate limit (records the request) → stream. Rejected requests never reach the graph. Only requests that pass every guard count against the rate limit. | Cheap, stateless checks come first. Invalid or over-budget requests do not burn a visitor's quota. Reading the body with a cap blocks oversized bodies even without `Content-Length`. |
| D9 | **Rate limiting and the spend cap are in-memory, per process.** That is the only implementation in scope. On Cloud Run with `min-instances=0`, a restart or scale-to-zero resets the counters, and several instances each keep their own. This is a documented limitation: the defences are spec 011's settings (`max-instances=1`), the billing alerts (handoff 7) and an OpenRouter per-key credit limit (an owner action). The app must run with a single uvicorn worker. Shared or persistent state (for example Firestore or Redis) is a *Future Consideration*. | Spec 011 is not built. A shared store adds a paid or managed dependency and ops work for a demo (handoff 12: stop before recurring cost). Python asyncio is single-threaded and no `await` sits between check and record, so no locks are needed. |
| D10 | **Rate limits per client IP:** a sliding 60-second window (`CHAT_RATE_PER_MINUTE`, default 5) plus a per-UTC-day count (`CHAT_RATE_PER_DAY`, default 50). Day is checked first. `Retry-After` is the seconds until the oldest request leaves the minute window, or until the next UTC midnight. At most `MAX_TRACKED_CLIENTS = 10000` keys are kept, and the least recently seen key is evicted first. **Owner review item #2** (the default values). | Handoff 7: "a few requests per minute, a daily cap". UTC days make the reset time the same for every visitor and easy to test. The eviction bound keeps memory finite under an IP-rotation attack, which the global spend cap backs up. |
| D11 | **Client IP:** with `CHAT_TRUSTED_PROXY_HOPS = n` (default 0), the IP is the n-th entry from the right of `X-Forwarded-For`. With `n = 0`, or when the header has fewer than `n` entries, it is the socket peer address (`"unknown"` if none). The limiter stores `HMAC-SHA256(per-process random salt, ip)[:32 hex]`, never the raw IP. | Behind Cloud Run every socket peer is Google's front end, so without proxy hops all visitors would share one bucket. Taking entries from the right ignores values a client prepends. Spec 011 sets and verifies the value for Cloud Run (open risk b). Hashing keeps raw IPs out of memory dumps; handoff 7 forbids IPs in traces, and they are never logged either (D17). |
| D12 | **Spend cap = sum of provider-reported `cost_usd` of completed LLM calls in the current UTC day** (`CHAT_DAILY_BUDGET_USD`, default 1.00). A request is rejected when `spent_today >= cap`. Costs are captured by `MeteredLLMClient`, a wrapper over the `LLMClient` port that `build_runtime` installs when it gets the new `on_llm_cost` callback. When a response has `cost_usd is None`, it counts `FALLBACK_CALL_COST_USD = 0.01` and logs one WARNING per process. Failed calls (`PortError`) count nothing. Query embeddings (about $0.0000006 each, spec 007 D1) are not counted. **Owner review item #2** (the default value). | Handoff 7: "a counter checked before each request". The cap can overshoot by the cost of the turns already in flight: at most three calls each (spec 006), about $0.01 per turn with the provisional spec 007 models. That is acceptable for a demo cap. The fallback value is deliberately high, so a provider that omits cost uses up the budget faster instead of bypassing it. A port wrapper keeps the graph and adapters unaware of budgets. |
| D13 | **Turn timeout `TURN_TIMEOUT_S = 60`** around the whole stream (`asyncio.timeout`). When it expires, the stream ends with `error` `timeout`. Unexpected exceptions end it with `error` `internal_error`, whose message is spec 006's `ERROR_TEXT`, and are logged with the trace id. A graph error reply (`PortError`, invalid LLM output) is a normal `reply` event with `kind: "error"`. | Worst case without a timeout is about three minutes (3 calls × 30 s × 2 attempts, spec 007 D12). Spec 006 D19: anything other than `PortError` is a bug, so the API maps it to an error event, not a crash mid-stream. |
| D14 | **App factory `create_app(...)`, run by `uvicorn backend.api.app:create_app --factory`.** Settings are read when `create_app` is called (`ConfigError` on invalid values). The runtime is built in the lifespan startup (fail-fast, spec 007 D23) and closed at shutdown. OpenAPI and docs routes are disabled. The uvicorn access log is turned off in the documented commands. | There are no import-time side effects, and tests inject a runtime over spec 006 fakes. Docs routes are unneeded public surface. Uvicorn's access log records client IPs (D17). |
| D15 | **The widget is a vanilla TypeScript island**: an Astro component with a processed `<script>` that calls `mountChatWidget()`. There is no UI-framework integration. It lives on a dedicated page `/assistant/`, which the header links to. Links in answers open in a new tab. **Owner review item #3** (dedicated page and new-tab links). | Spec 004 D4 has no Astro integrations, and handoff 4.5 says "keep it light". One form and a list need no framework. Each page is a full navigation on a static site, so a widget on every page would lose the conversation on every citation click. A dedicated page with new-tab links keeps the transcript, avoids storage, and keeps rules pages script-free. |
| D16 | **Rendering is safe by construction.** All server text goes into `textContent`, never `innerHTML`. Every `href` is built client-side with spec 004's `sectionUrl`/`moveUrl`. The protocol schema also requires each payload `url` to equal that value, otherwise the payload is malformed. Each `[[id]]` marker becomes a numbered link `[n]` to the n-th citation; markers not in `citations` are dropped. | The payload contains LLM text, so it is treated as untrusted. Spec 004 makes `urls.ts` the only place URLs are built, so a `javascript:` or off-site href cannot exist. Spec 006 D12 left marker-to-link replacement to this spec. |
| D17 | **Privacy:** no raw IP in traces, logs or rate-limiter memory. The API logs only rejection codes, trace ids and exception classes, never the message text. The user message reaches Langfuse through spec 007's generation inputs by design (spec 007 tracing ADR). | Handoff 7. Spec 007's `Tracer` already carries only `trace_id`/`session_id`. |
| D18 | **One cross-stack contract fixture**, `backend/tests/fixtures/chat_reply_examples.json` (exact content in *Data Model*). A backend test asserts that `reply_payload` produces exactly those objects, and a frontend test asserts that the protocol schema parses them and the renderer handles them. | One file binds both halves of the contract. Spec 004 already reads data from outside `site/` (`data/normalized/`), so a site test reading a backend fixture follows that precedent. |
| D19 | **DOM tests use `happy-dom`** (new site devDependency; per-file `// @vitest-environment happy-dom`). Pure modules (`sse.ts`, `protocol.ts`, `client.ts`) are tested in the default `node` environment. PR line: *"happy-dom: lightweight DOM for Vitest so the widget's rendering and escaping are tested without a browser."* | Spec 004 D7 uses Vitest with `environment: "node"`. Escaping and link building are security properties and need real DOM assertions. |
| D20 | **ADR numbers:** the next free numbers in `docs/decisions.md` at implementation time. | Spec 005 D16 / 006 D26 / 007 D25 precedent. |

**Open risks.**
- (a) **Per-instance counters (D9).** Until spec 011 sets `max-instances=1` and the owner sets an OpenRouter key credit limit, a restart or a second instance can let daily spend exceed `CHAT_DAILY_BUDGET_USD`. This is stated in the API ADR and in spec 011's inputs.
- (b) **Cloud Run `X-Forwarded-For` layout (D11)** is assumed to end with the client IP (hops = 1). Spec 011 must verify it live. If it is wrong, limits apply per proxy instead of per visitor. That is safe on cost (the global cap still holds) but unfair to visitors.
- (c) **LangGraph `astream` with two stream modes** is assumed to yield `(mode, chunk)` tuples, where `updates` chunks are `{node_name: update}`. This is the same version risk as spec 006 open risk (a), confined to `builder.py`. `test_stream_result_equals_run_result` catches any drift.
- (d) **SSE through the Vite dev proxy** (http-proxy) is expected to pass chunks through unbuffered. If it buffers, only local progress display is affected (the reply still arrives). The manual check in *Success Criteria* covers it.
- (e) **eslint-plugin-astro and browser globals.** The component script references no globals (it only imports and calls `mountChatWidget()`), so `no-undef` cannot fire on it.

## Architecture / Design Overview

```
Browser /assistant/  (site/src/pages/assistant.astro → ChatWidget.astro → mountChatWidget)
   │ fetch POST /api/chat  {message, roll, modifier, session_id}   Content-Type: application/json
   │   dev: astro dev :4321 ──Vite proxy /api──▶ uvicorn :8000      prod: same container (spec 011)
   ▼
backend/api/app.py  POST /api/chat
   415 content type ─▶ 413 body > 16 KiB ─▶ 422 schema / message ─▶ 503 budget ─▶ 429 rate limit
   │ (all JSON {"error": {code, message}}, no LLM call)                 SpendLedger   RateLimiter
   ▼ 200 text/event-stream                                                 ▲             (in-memory,
Assistant.stream(TurnInput)  ── NodeCompleted ──▶ event: status {"step"}   │ record(cost) per process)
   │ (spec 006 graph; LangGraph astream inside builder.py only)            │
   │   LLMClient = MeteredLLMClient(OpenRouterLLMClient) ──────────────────┘ (spec 007 build_runtime
   └─ TurnResult ──reply_payload──▶ event: reply {trace_id, kind, text, citations, move}   on_llm_cost hook)
      timeout / bug ─────────────▶ event: error {code, message}
GET /api/health ─▶ 200 {"status": "ok"}
```

Widget flow: on submit, `mountChatWidget` validates the input, appends the user's message to the log and calls `sendChat`. `sendChat` maps each `status` event to progress copy and returns either a `reply` (rendered by `renderReply`: paragraphs with `[n]` links, a sources list and a move card) or a failure (rendered as an error message, with the typed text restored).

Layering: `backend/api/` imports `fastapi`/`starlette`/`pydantic`, the stdlib, `backend.graph.{builder,state,replies}`, `backend.ports.*`, `backend.domain.*` and `backend.composition`. It never imports `backend.adapters` or `langgraph`. No other backend package imports `fastapi`, `starlette` or `backend.api`.

## Configuration

**Environment variables** (read only by `backend/api/settings.py`; empty or whitespace-only means the default):

| Variable | Default | Valid values | Meaning |
|----------|---------|--------------|---------|
| `CHAT_RATE_PER_MINUTE` | `5` | int 1…1000 | Accepted chat requests per client per rolling 60 s (D10). |
| `CHAT_RATE_PER_DAY` | `50` | int 1…100000 | Accepted chat requests per client per UTC day (D10). |
| `CHAT_DAILY_BUDGET_USD` | `1.00` | finite float, 0 < x ≤ 1000 | Global LLM spend cap per UTC day (D12). |
| `CHAT_TRUSTED_PROXY_HOPS` | `0` | int 0…5 | `X-Forwarded-For` entries to trust from the right (D11). |

The spec 007 variables (`OPENROUTER_API_KEY`, `MODEL_*`, `LANGFUSE_*`) are still required by the default runtime factory.

**`.env.example`** (modify, additive). Append at the end:

```dotenv
# Chat API guardrails (spec 008). Leave empty for the default in brackets.
# Accepted /api/chat requests per client IP per rolling minute [5].
CHAT_RATE_PER_MINUTE=
# Accepted /api/chat requests per client IP per UTC day [50].
CHAT_RATE_PER_DAY=
# Global LLM spend cap per UTC day, in USD [1.00]. In-memory per process (see docs/decisions.md).
CHAT_DAILY_BUDGET_USD=
# X-Forwarded-For entries added by trusted proxies, counted from the right [0 = use the socket peer].
CHAT_TRUSTED_PROXY_HOPS=
```

**Constants** (not env-configurable): `MAX_MESSAGE_CHARS = 500`, `MAX_BODY_BYTES = 16384`, `TURN_TIMEOUT_S = 60.0`, `MAX_TRACKED_CLIENTS = 10000` (`backend/api/settings.py`). `FALLBACK_CALL_COST_USD = 0.01` (`backend/adapters/metered_llm.py`). Site: `CHAT_ENDPOINT = "/api/chat"` and `MAX_MESSAGE_CHARS = 500` (`site/src/lib/chat/client.ts`); `API_PROXY_TARGET = "http://127.0.0.1:8000"` (`site/astro.config.ts`).

**`pyproject.toml`** (additive): `uv add fastapi uvicorn` appends two `"<name>>=<resolved version>"` entries to `[project].dependencies` and updates `uv.lock`. No tool-config change.

**`site/package.json`** (additive): `npm install --save-dev happy-dom` (caret range); lockfile regenerated. No script changes.

**`site/astro.config.ts`** (additive): add `vite: { server: { proxy: { "/api": { target: API_PROXY_TARGET, changeOrigin: false } } } }`. Existing `output`, `trailingSlash` and `build` settings are unchanged. The proxy affects only `astro dev`.

## Data Model

No database. In-memory state lives for the process lifetime (D9).

### Backend types

```python
# backend/graph/state.py   (modified, additive)
class NodeCompleted:                     # frozen dataclass; node non-empty
    node: str                            # one of the 11 spec 006 node names
AssistantEvent = NodeCompleted | TurnResult

# backend/graph/builder.py   (modified, additive)
class Assistant:
    async def run(self, turn: TurnInput) -> TurnResult: ...            # unchanged behaviour
    def stream(self, turn: TurnInput) -> AsyncIterator[AssistantEvent]: ...
    # async generator: NodeCompleted per executed node in execution order, then exactly one
    # TurnResult (equal to what run() returns for the same deps and input); RuntimeError
    # "graph finished without a reply" if the final state has no reply

# backend/adapters/metered_llm.py   (new)
FALLBACK_CALL_COST_USD: Final = 0.01
class MeteredLLMClient:                  # satisfies ports.llm.LLMClient
    def __init__(self, inner: LLMClient, on_cost: Callable[[float], None],
                 fallback_cost_usd: float = FALLBACK_CALL_COST_USD) -> None: ...
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    # returns inner's response unchanged; on success calls on_cost(cost_usd or fallback);
    # PortError propagates and nothing is recorded

# backend/composition.py   (modified, additive)
def build_runtime(settings: Settings, *, ..., on_llm_cost: Callable[[float], None] | None = None) -> Runtime: ...

# backend/api/settings.py   (new)
API_ENV_VARS: Final[tuple[str, ...]]     # the four names in Configuration, in table order
class ApiSettings:                       # frozen dataclass
    rate_per_minute: int = 5; rate_per_day: int = 50
    daily_budget_usd: float = 1.0; trusted_proxy_hops: int = 0
    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> ApiSettings: ...   # ConfigError (spec 007) listing all problems

# backend/api/limits.py   (new)
Clock = Callable[[], float]              # epoch seconds (time.time)
class RateDecision:                      # frozen dataclass
    allowed: bool; scope: Literal["minute", "day"] | None; retry_after_s: int | None
class RateLimiter:
    def __init__(self, per_minute: int, per_day: int, clock: Clock,
                 max_clients: int = MAX_TRACKED_CLIENTS) -> None: ...
    def check(self, key: str) -> RateDecision: ...     # records the request only when allowed
class SpendLedger:
    def __init__(self, daily_cap_usd: float, clock: Clock) -> None: ...
    def record(self, cost_usd: float) -> None: ...     # ValueError if negative or non-finite
    def spent_today(self) -> float: ...
    def exhausted(self) -> bool: ...                   # spent_today() >= cap
def seconds_until_utc_midnight(now: float) -> int: ...  # ceil, >= 1
def client_ip(headers: Mapping[str, str], peer_host: str | None, hops: int) -> str: ...
class ClientKeyer:
    def __init__(self, salt: bytes | None = None) -> None: ...   # default secrets.token_bytes(16)
    def key(self, ip: str) -> str: ...                            # 32 lowercase hex

# backend/api/schemas.py   (new)
class ChatRequest(pydantic.BaseModel):   # model_config = ConfigDict(extra="forbid", strict=True)
    message: str
    roll: bool = False
    modifier: int | None = Field(default=None, ge=-10, le=10)
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
def reply_payload(result: TurnResult, trace_id: str) -> dict[str, JsonValue]: ...
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after_s: int | None = None) -> None: ...

# backend/api/sse.py   (new)
def sse_event(event: str, data: Mapping[str, JsonValue]) -> bytes: ...
# f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n" UTF-8;
# ValueError if event is not ^[a-z_]+$

# backend/api/app.py   (new)
CostSink = Callable[[float], None]
RuntimeFactory = Callable[[CostSink], Runtime]
def create_app(*, environ: Mapping[str, str] | None = None,       # default os.environ
               runtime_factory: RuntimeFactory | None = None,     # default: build_runtime(Settings.from_env(environ), on_llm_cost=sink)
               clock: Clock = time.time,
               keyer: ClientKeyer | None = None,
               turn_timeout_s: float = TURN_TIMEOUT_S) -> FastAPI: ...
```

### Wire contract

**Error body** (every non-200 response from `/api/chat` produced by this spec): `{"error": {"code": str, "message": str}}`.

**SSE events** (`Content-Type: text/event-stream; charset=utf-8`):

| Event | `data` | When |
|-------|--------|------|
| `status` | `{"step": "<node>"}`, where node is one of `router`, `out_of_scope`, `retrieve`, `answer_with_citations`, `citation_validator`, `classify_move`, `clarify`, `no_move`, `explain`, `roll`, `outcome` | After each node completes, in execution order. |
| `reply` | The reply payload below | Last event of a completed turn. |
| `error` | `{"code": "timeout" \| "internal_error", "message": str}` | Last event of a failed turn (D13). |

**Reply payload** (`reply_payload`; key order as listed):

| Key | Value |
|-----|-------|
| `trace_id` | The server-generated 32-hex trace id. |
| `kind` | `Reply.kind` (spec 006 `ReplyKind`, seven values). |
| `text` | `Reply.text` verbatim, including kept `[[section_id]]` markers. |
| `citations` | List of `{"section_id", "title", "url"}` in `Reply.citations` order. |
| `move` | `null`, or `{"move_id", "name", "url", "trigger", "stat", "roll_stat", "outcomes", "roll", "outcome", "bands_by_modifier"}`. `stat` is spec 002's `Stat` or `null`; `roll_stat` is an `AbilityStat` or `null`. `outcomes` is `null` or `{"strong_hit", "weak_hit", "miss"}` (miss may be `null`). `roll` is `null` or `{"dice": [d1, d2], "modifier": int \| null, "total": int \| null}`. `outcome` is `null` or `{"band": Band, "text": str \| null}`. `bands_by_modifier` is a list of `{"modifier": int, "band": Band}` (empty unless rolled without a modifier). |

`TurnResult.intent`, `router_confidence`, `classification` and `retrieved_section_ids` are not exposed. They are for evals (spec 009), which call `Assistant` directly.

**Contract fixture** `backend/tests/fixtures/chat_reply_examples.json` (new, exact content; UTF-8, `indent=2`, trailing newline):

```json
{
  "rules_answer": {
    "trace_id": "0123456789abcdef0123456789abcdef",
    "kind": "rules_answer",
    "text": "Deal your damage [[moves/hack-and-slash]].\n\nTo avoid a blow, Defy Danger [[moves/defy-danger]].",
    "citations": [
      {"section_id": "moves/hack-and-slash", "title": "Hack and Slash", "url": "/rules/moves/hack-and-slash/"},
      {"section_id": "moves/defy-danger", "title": "Defy Danger", "url": "/rules/moves/defy-danger/"}
    ],
    "move": null
  },
  "rules_not_found": {
    "trace_id": "11111111111111111111111111111111",
    "kind": "rules_not_found",
    "text": "I couldn't find this in the rules.",
    "citations": [
      {"section_id": "moves/last-breath", "title": "Last Breath", "url": "/rules/moves/last-breath/"}
    ],
    "move": null
  },
  "move_rolled_with_modifier": {
    "trace_id": "22222222222222222222222222222222",
    "kind": "move",
    "text": "Attacking the goblin in melee triggers Hack and Slash.\n\nRolled 4 + 5 + 1 = 10: 10+.",
    "citations": [],
    "move": {
      "move_id": "hack-and-slash",
      "name": "Hack and Slash",
      "url": "/moves/hack-and-slash/",
      "trigger": "When you attack an enemy in melee",
      "stat": "STR",
      "roll_stat": "STR",
      "outcomes": {"strong_hit": "On a 10+ you deal your damage.", "weak_hit": "On a 7-9 you deal your damage and the enemy attacks you.", "miss": null},
      "roll": {"dice": [4, 5], "modifier": 1, "total": 10},
      "outcome": {"band": "strong_hit", "text": "On a 10+ you deal your damage."},
      "bands_by_modifier": []
    }
  },
  "move_rolled_without_modifier": {
    "trace_id": "33333333333333333333333333333333",
    "kind": "move",
    "text": "Leaping the chasm under fire triggers Defy Danger.\n\nRolled 3 + 5 = 8. Add your modifier: -3 to -2: 6-; -1 to +1: 7-9; +2 to +3: 10+.",
    "citations": [],
    "move": {
      "move_id": "defy-danger",
      "name": "Defy Danger",
      "url": "/moves/defy-danger/",
      "trigger": "When you act despite an imminent threat",
      "stat": "VARIES",
      "roll_stat": null,
      "outcomes": {"strong_hit": "On a 10+, you do what you set out to.", "weak_hit": "On a 7-9, you stumble or hesitate.", "miss": null},
      "roll": {"dice": [3, 5], "modifier": null, "total": null},
      "outcome": null,
      "bands_by_modifier": [
        {"modifier": -3, "band": "miss"}, {"modifier": -2, "band": "miss"},
        {"modifier": -1, "band": "weak_hit"}, {"modifier": 0, "band": "weak_hit"},
        {"modifier": 1, "band": "weak_hit"}, {"modifier": 2, "band": "strong_hit"},
        {"modifier": 3, "band": "strong_hit"}
      ]
    }
  }
}
```

### Frontend types (`site/src/lib/chat/protocol.ts`)

Zod schemas are non-strict (unknown keys are stripped) so new server fields stay compatible. They mirror the wire contract above:

```ts
export type ReplyKind = "rules_answer" | "rules_not_found" | "move" | "no_move" | "clarification" | "out_of_scope" | "error";
export type Band = "strong_hit" | "weak_hit" | "miss";
export interface Citation { section_id: string; title: string; url: string }      // url === sectionUrl(section_id)
export interface MoveCardPayload { move_id: string; name: string; url: string;      // url === moveUrl(move_id)
  trigger: string; stat: Stat | null; roll_stat: AbilityStat | null;
  outcomes: { strong_hit: string; weak_hit: string; miss: string | null } | null;
  roll: { dice: [number, number]; modifier: number | null; total: number | null } | null;
  outcome: { band: Band; text: string | null } | null;
  bands_by_modifier: { modifier: number; band: Band }[] }
export interface ChatReply { trace_id: string; kind: ReplyKind; text: string; citations: Citation[]; move: MoveCardPayload | null }
export const replySchema, statusSchema /* {step: string} */, streamErrorSchema /* {code, message} */,
             httpErrorSchema /* {error: {code, message}} */;
```

`Stat` is spec 004's union from `rulebook.ts`; `AbilityStat` = `"STR" | "DEX" | "CON" | "INT" | "WIS" | "CHA"`.

## Impact on Existing Code

The work splits across two feature-builders. Backend rows are implemented by `python-feature-builder`, `site/` rows by `astro-feature-builder` (spec 003). See *Suggested Story Breakdown*.

| Path | Action | Notes |
|------|--------|-------|
| `backend/graph/state.py` (new in 006) | modify — **additive** | Add `NodeCompleted` and `AssistantEvent`. Existing types are unchanged. |
| `backend/graph/builder.py` (new in 006) | modify — **additive** | Add `Assistant.stream` (D4). The state-to-`TurnResult` conversion that `run` uses is extracted into a private helper shared by both. `run`'s behaviour, signature and the `compiled` / `_assistant_from_compiled` seams are unchanged, and every spec 006 test passes unmodified. |
| `backend/adapters/metered_llm.py` (new) | create | `MeteredLLMClient` (D12). Imports only `backend.ports.*`, `logging`, `math`, stdlib typing. |
| `backend/composition.py` (new in 007) | modify — **additive** | Keyword-only `on_llm_cost=None` on `build_runtime`. When set, the chat `OpenRouterLLMClient` is wrapped in `MeteredLLMClient` before `GraphDeps`. With `None`, the behaviour is identical, so `backend/chat.py` (new in 007) and every spec 007 test are unaffected. |
| `backend/api/__init__.py` (new in 001) | unchanged | Stays empty. |
| `backend/api/settings.py` (new) | create | `ApiSettings`, `API_ENV_VARS`, constants. |
| `backend/api/limits.py` (new) | create | `RateLimiter`, `SpendLedger`, `client_ip`, `ClientKeyer`, `seconds_until_utc_midnight`. |
| `backend/api/schemas.py` (new) | create | `ChatRequest`, `reply_payload`, `ApiError`. |
| `backend/api/messages.py` (new) | create | API copy constants (*User-Facing Copy*). |
| `backend/api/sse.py` (new) | create | `sse_event`. |
| `backend/api/app.py` (new) | create | `create_app`, lifespan, routes, `ApiError` handler. |
| `backend/tests/fixtures/chat_reply_examples.json` (new) | create | Contract fixture (D18). |
| `backend/tests/api_helpers.py` (new) | create | *Testing* helpers. Not collected by pytest. |
| `backend/tests/test_graph_stream.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_metered_llm.py` (new) | create | *Testing*. |
| `backend/tests/test_api_settings.py` (new) | create | *Testing*. |
| `backend/tests/test_api_limits.py` (new) | create | *Testing*. |
| `backend/tests/test_api_sse.py` (new) | create | *Testing*. |
| `backend/tests/test_api_contract.py` (new) | create | *Testing*. |
| `backend/tests/test_api_chat.py` (new) | create | *Testing*. |
| `backend/tests/test_api_validation.py` (new) | create | *Testing*. |
| `backend/tests/test_api_guardrails.py` (new) | create | *Testing*. |
| `backend/tests/test_api_layering.py` (new) | create | *Testing*. |
| `backend/tests/test_composition.py` (new in 007) | modify — **additive** | Add `test_build_runtime_meters_llm_cost`. Existing tests untouched. |
| `backend/tests/fakes/*`, `graph_helpers.py`, `domain_helpers.py`, `adapter_helpers.py`, `conftest.py` (new in 005/006/007) | unchanged | Reused. The socket guard stays active: `TestClient` uses an in-memory transport. |
| `pyproject.toml`, `uv.lock` (new in 001) | modify — **additive** | `fastapi`, `uvicorn` (D5). |
| `.env.example` (new in 001) | modify — **additive** | Four keys (*Configuration*). Every line still matches spec 001's `KEY=` pattern and keys stay unique, so `test_env_example_declares_keys_without_values` keeps passing. |
| `site/src/lib/chat/sse.ts` (new) | create | SSE parser (*Widget Behaviour*). |
| `site/src/lib/chat/protocol.ts` (new) | create | Zod schemas and types (*Data Model*). |
| `site/src/lib/chat/client.ts` (new) | create | `sendChat`, `CHAT_ENDPOINT`, `MAX_MESSAGE_CHARS`. |
| `site/src/lib/chat/copy.ts` (new) | create | Widget copy (*User-Facing Copy*). |
| `site/src/lib/chat/render.ts` (new) | create | `segmentText`, `renderReply`, `renderUserMessage`, `renderFailure`, `diceText`. |
| `site/src/lib/chat/widget.ts` (new) | create | `mountChatWidget`. |
| `site/src/components/ChatWidget.astro` (new) | create | Markup and client script. |
| `site/src/pages/assistant.astro` (new) | create | `/assistant/` page. |
| `site/src/lib/urls.ts` (new in 004) | modify — **additive** | Add `ASSISTANT_URL = "/assistant/"`. Existing exports unchanged. |
| `site/src/lib/format.ts` (new in 004) | modify — **additive** | Add `bandLabel(band)`: `"10+ (strong hit)"`, `"7–9 (weak hit)"` (en dash), `"6- (miss)"`, the same strings as the spec 004 move page. The move page is not changed. |
| `site/src/components/SiteHeader.astro` (new in 004) | modify — **additive** | Third nav link "Assistant" → `ASSISTANT_URL`, with `aria-current` per the existing rule. Existing links unchanged. |
| `site/src/styles/global.css` (new in 004) | modify — **additive** | `.visually-hidden` and widget styles (*Widget Behaviour*). Existing rules unchanged. |
| `site/astro.config.ts` (new in 004) | modify — **additive** | Dev proxy (*Configuration*). |
| `site/package.json`, `site/package-lock.json` (new in 001/004) | modify — **additive** | `happy-dom` devDependency. Script names unchanged (spec 001 D11 contract). |
| `site/tests/unit/chat-sse.test.ts`, `chat-protocol.test.ts`, `chat-client.test.ts`, `chat-render.test.ts`, `chat-widget.test.ts`, `format.test.ts` (new; `format.test.ts` new in 004) | create / modify (additive for `format.test.ts`) | *Testing*. |
| `site/tests/dist/site.test.ts` (new in 004) | modify — **additive** | Two cases (*Testing*). Existing cases unchanged. The link check (`checkSite`) covers the new page automatically. |
| `docs/decisions.md`, `docs/architecture.md`, `README.md` (new in 001, extended by 004–007) | modify — **additive** | *Documentation*. README `## Attribution` untouched. |

Spec 004's statement "no client-side JavaScript" described that spec's scope, not a contract. Rules pages stay script-free, and only `/assistant/` loads a script. CI (`ci.yml`) needs no change: the new Python tests run in `uv run pytest`, and the site tests run in `npm test` / `npm run check-links`. It still references no secrets.

## API Behaviour

### `GET /api/health`

Returns 200 `{"status": "ok"}` with `Cache-Control: no-store`. It has no guards, does not touch the runtime and is never rate limited. It returns 200 even when the budget is exhausted.

### `POST /api/chat`

Handler signature: `async def chat(request: Request) -> Response`. Guards run in D8 order. Each one raises `ApiError`, which an app-level exception handler turns into a `JSONResponse` with the *Error body*, `Cache-Control: no-store`, and `Retry-After: <n>` when `retry_after_s` is set. Each rejection logs INFO `chat request rejected: <code>` on logger `backend.api`.

| # | Check | Failure |
|---|-------|---------|
| 1 | `Content-Type` media type (before `;`) case-insensitively equals `application/json` | 415 `unsupported_media_type` |
| 2 | `Content-Length`, if present, ≤ `MAX_BODY_BYTES`. Then read `request.stream()` and accumulate, stopping as soon as the total exceeds `MAX_BODY_BYTES`. | 413 `request_too_large` |
| 3 | `ChatRequest.model_validate_json(body)` succeeds (invalid UTF-8, invalid JSON, non-object, missing `message`, extra key, wrong type, out-of-range `modifier`, bad `session_id`) | 422 `invalid_request` |
| 4 | `message.strip()` is non-empty | 422 `invalid_request` |
| 5 | `len(message.strip()) <= MAX_MESSAGE_CHARS` | 422 `message_too_long` |
| 6 | `not ledger.exhausted()` | 503 `budget_exhausted`, `Retry-After` = `seconds_until_utc_midnight(now)` |
| 7 | `limiter.check(keyer.key(client_ip(headers, request.client.host, hops)))` is allowed | 429 `rate_limited`; the message depends on `scope` (*User-Facing Copy*); `Retry-After` = `retry_after_s` |

Then:
- Build `TurnInput(message=stripped, session_id=req.session_id or uuid4().hex, trace_id=uuid4().hex, roll_requested=req.roll, modifier=req.modifier)`.
- Return `StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})`.

The `gen()` async generator works as follows:

```
async with asyncio.timeout(turn_timeout_s):
    async for ev in runtime.assistant.stream(turn):
        NodeCompleted → yield sse_event("status", {"step": ev.node})
        TurnResult    → yield sse_event("reply", reply_payload(ev, turn.trace_id))
except TimeoutError → log WARNING "chat turn timed out trace_id=<id>"; yield error {"code": "timeout", "message": TIMEOUT_TEXT}
except Exception    → log ERROR "chat turn failed: <ClassName> trace_id=<id>" (exc_info); yield error {"code": "internal_error", "message": ERROR_TEXT}
```

`CancelledError` (client disconnect) is not caught. The graph run is cancelled with the response task, and only completed LLM calls were metered.

### Lifespan and wiring (`create_app`)

1. `environ = os.environ if environ is None else environ` (an explicit `{}` is respected). Build `api_settings = ApiSettings.from_env(environ)`, which raises `ConfigError` here.
2. Create `ledger = SpendLedger(api_settings.daily_budget_usd, clock)`, `limiter = RateLimiter(api_settings.rate_per_minute, api_settings.rate_per_day, clock)`, and `keyer = keyer or ClientKeyer()`.
3. Construct `FastAPI(lifespan=..., docs_url=None, redoc_url=None, openapi_url=None)`. The lifespan calls `runtime = runtime_factory(ledger.record)`. The default factory is `lambda sink: build_runtime(Settings.from_env(environ), on_llm_cost=sink)`, so startup fails on bad config or a missing index. The runtime is stored on `app.state`; after `yield`, the lifespan runs `await runtime.aclose()`.
4. Register the two routes and the `ApiError` handler. There is no CORS middleware.

### Limits (`limits.py`)

- `RateLimiter.check(key)`, where `now = clock()` and `today = UTC date of now`:
  1. Drop the key's stored day count if its date ≠ today.
  2. If `day_count >= per_day`, return `(False, "day", seconds_until_utc_midnight(now))`.
  3. Drop minute timestamps `<= now - 60`. If `len >= per_minute`, return `(False, "minute", max(1, ceil(oldest + 60 - now)))`.
  4. Otherwise append `now`, increment the day count, move the key to most-recent, and evict the least-recent key while the number of keys exceeds `max_clients`. Return `(True, None, None)`.
- `SpendLedger` keeps `(date, total)`. `record` and `spent_today` reset the total when the UTC date of `clock()` changes.
- `client_ip`: with `hops == 0`, return `peer_host or "unknown"`. Otherwise split `X-Forwarded-For` (header lookup is case-insensitive) on `,`, strip the parts and drop empty ones. If there are at least `hops` parts, return `parts[-hops]`, else `peer_host or "unknown"`.
- `ClientKeyer.key(ip)` = `hmac.new(salt, ip.encode(), sha256).hexdigest()[:32]`.

### `MeteredLLMClient` and composition

`generate` awaits `inner.generate(request)`. On success, it uses `cost = response.cost_usd`. If that is `None`, it uses `fallback_cost_usd` instead, and logs WARNING `LLM response had no cost; counting fallback <x> USD` on logger `backend.adapters.metered_llm` (once per instance). It then calls `on_cost(cost)` and returns the same response object. `PortError` propagates without calling `on_cost`. In `build_runtime`, step 3 of spec 007 becomes `llm = OpenRouterLLMClient(...)`, then `llm = MeteredLLMClient(llm, on_llm_cost)` if `on_llm_cost` is not `None`. The tracer still records the same `LLMResponse`.

### `Assistant.stream` (`builder.py`)

The method iterates `compiled.astream({"turn": turn}, stream_mode=["updates", "values"])`:
- For each `("updates", chunk)`, it yields `NodeCompleted(name)` for each key of `chunk` that is one of the 11 node names, in key order.
- For each `("values", state)`, it keeps `state` as the latest state.

After the loop, it builds the `TurnResult` from the latest state with the same private helper as `run`. If `reply` is missing, it raises `RuntimeError("graph finished without a reply")`. Otherwise it yields the result.

## Widget Behaviour

### Page and component

**`assistant.astro`** (`/assistant/`, `BaseLayout` title "Assistant"):
- `<h1>Rules assistant</h1>`.
- The intro paragraph (*User-Facing Copy*).
- `<ChatWidget />`.

**`ChatWidget.astro`** markup, in this order, inside `<section id="chat" class="chat" aria-labelledby="chat-heading">`:

1. `<h2 id="chat-heading" class="visually-hidden">Conversation</h2>`.
2. `<ol id="chat-log" class="chat-log" role="log" aria-label="Conversation"></ol>`.
3. `<p id="chat-status" class="chat-status" role="status"></p>`.
4. `<form id="chat-form" novalidate>` containing:
   - `<label for="chat-message">Your message</label>`.
   - `<textarea id="chat-message" name="message" rows="3" maxlength="500" required aria-describedby="chat-count chat-message-error"></textarea>`.
   - `<p id="chat-count" class="chat-count">0/500</p>`.
   - `<p id="chat-message-error" class="chat-field-error" hidden></p>`.
   - `<label><input type="checkbox" id="chat-roll" name="roll"> Roll the dice for me</label>`.
   - `<label for="chat-modifier">Modifier (optional)</label> <input type="number" id="chat-modifier" name="modifier" min="-10" max="10" step="1" inputmode="numeric" disabled aria-describedby="chat-modifier-error">`.
   - `<p id="chat-modifier-error" class="chat-field-error" hidden></p>`.
   - `<button type="submit" id="chat-submit">Ask</button>`.
5. `<noscript><p>The assistant needs JavaScript. The rules pages work without it.</p></noscript>`.
6. `<script>import { mountChatWidget } from "../lib/chat/widget"; mountChatWidget();</script>`.

The `500` in the markup must equal `MAX_MESSAGE_CHARS`: the component interpolates the constant.

**CSS** (`global.css`, additive):
- `.visually-hidden` (the standard clip pattern).
- `.chat-log` has no list markers.
- `.chat-user` is right-aligned and `.chat-assistant` left-aligned, with a light border.
- `.chat-text p { white-space: pre-line }`.
- `.chat-error` has a border plus the text prefix (see *Rendering*), not colour alone.
- `.move-card` is a bordered block, and its `.is-result` band is bold.
- Focus outlines stay visible (spec 004).

### `sse.ts`

```ts
export interface SseMessage { event: string; data: string }
export class SseParser { feed(chunk: string): SseMessage[]; }   // incremental
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage>;
```

The parser follows the WHATWG event-stream rules:
- Lines end with `\n`, `\r\n` or `\r`, including line ends split across chunks.
- Lines starting with `:` are comments and are ignored.
- `field: value` loses one leading space from the value. `event` sets the name, and `data` lines are joined with `\n`. Other fields are ignored.
- A blank line dispatches the message if the data buffer is non-empty (event defaults to `"message"`), then resets.

`readSse` decodes with a streaming `TextDecoder("utf-8")`. At end of stream, an undispatched partial event is discarded.

### `client.ts`

```ts
export const CHAT_ENDPOINT = "/api/chat";
export const MAX_MESSAGE_CHARS = 500;
export interface ChatRequestBody { message: string; roll: boolean; modifier: number | null; session_id: string }
export type ChatOutcome = { type: "reply"; reply: ChatReply } | { type: "failure"; code: string; message: string };
export async function sendChat(body: ChatRequestBody,
  opts?: { fetch?: typeof fetch; onStatus?: (step: string) => void; signal?: AbortSignal }): Promise<ChatOutcome>;
```

The request is `POST`, with headers `Content-Type: application/json` and `Accept: text/event-stream`, and the body `JSON.stringify(body)`. Outcome mapping:

| Situation | Outcome |
|-----------|---------|
| `fetch` rejects (not an abort) | failure `network`, `NETWORK_FAILURE` |
| non-2xx, and the body parses with `httpErrorSchema` | failure with the server's `code` and `message` |
| non-2xx, body unparseable | failure `http_<status>`, `UNAVAILABLE` |
| 2xx but no body, or `Content-Type` not `text/event-stream` | failure `malformed`, `INTERRUPTED` |
| `status` event that is valid JSON for `statusSchema` | `onStatus(step)`, continue |
| `reply` event valid for `replySchema` | return `reply`, then cancel the reader |
| `error` event valid for `streamErrorSchema` | failure with its code and message |
| `status`/`reply`/`error` with invalid JSON or schema | failure `malformed`, `INTERRUPTED` |
| unknown event name | ignored |
| stream ends without `reply`/`error`, or a read error | failure `interrupted`, `INTERRUPTED` |

### `render.ts`

```ts
export type Segment = { type: "text"; text: string } | { type: "citation"; index: number; citation: Citation };
export function segmentText(text: string, citations: readonly Citation[]): Segment[];
export function diceText(roll: NonNullable<MoveCardPayload["roll"]>): string;
export function renderUserMessage(doc: Document, text: string): HTMLLIElement;
export function renderReply(doc: Document, reply: ChatReply): HTMLLIElement;
export function renderFailure(doc: Document, message: string): HTMLLIElement;
```

- **`segmentText`.** Markers match `/\[\[([^\[\]\s]+)\]\]/g` (spec 006 D12). A marker whose id is the `section_id` of citation *i* (0-based) becomes `{citation, index: i + 1}`. Unknown markers produce nothing. Adjacent text is kept verbatim.
- **`renderUserMessage`.** `<li class="chat-user">`, containing a visually hidden `You: ` followed by the text node.
- **`renderReply`.** `<li class="chat-assistant" data-kind="<kind>">`, containing, in order:
  1. A visually hidden `Assistant: `.
  2. `<div class="chat-text">`. The text is split on `/\n{2,}/`; each paragraph becomes a `<p>` whose segments are text nodes or `<a href="<sectionUrl(id)>" target="_blank" rel="noopener noreferrer" aria-label="Source <n>: <title> (opens in a new tab)">[<n>]</a>`. With kind `error`, the first `<p>` starts with `<strong>Error: </strong>` and the `<li>` gets class `chat-error`.
  3. If `citations` is non-empty: `<p class="chat-sources-title">` with `CLOSEST_TITLE` for `rules_not_found` and `SOURCES_TITLE` otherwise, followed by an `<ol class="chat-sources">`. Each item is `<a href=sectionUrl target="_blank" rel="noopener noreferrer">title<span class="visually-hidden"> (opens in a new tab)</span></a>`.
  4. If `move` is non-null, the move card below.
- **Move card.** `<section class="move-card" aria-label="Move: <name>">` containing:
  - `<h3><a href="<moveUrl(move_id)>" target="_blank" rel="noopener noreferrer">name<span class="visually-hidden"> (opens in a new tab)</span></a></h3>`.
  - `<dl class="move-facts">` with `Trigger` → trigger and `Roll` → `rollLabel(roll_stat ?? stat)` (spec 004 `format.ts`; `VARIES` without a chosen stat gives "+stat chosen by how you act"). If `roll` is set, add `Dice` → `diceText(roll)`.
  - If `outcomes` is set: `<dl class="outcomes">` with three `dt`/`dd` pairs in strong, weak, miss order. Each `dt` is `bandLabel(band)`; each `dd` is the text, with `NOT_STATED` for a `null` miss. The pair whose band equals `outcome?.band` gets class `is-result` on both elements, and its `dt` gets the suffix `YOUR_ROLL`.
- **`diceText`.** With a modifier: `"4 + 5 + 1 = 10"`, or `"3 + 3 - 1 = 5"` for a negative one (sign `+`/`-`, absolute value). Without a modifier: `"3 + 5 = 8, before your modifier"`.
- **`renderFailure`.** `<li class="chat-assistant chat-error" data-kind="failure">`, containing a visually hidden `Assistant: `, then `<p><strong>Error: </strong>` + the message `</p>`.
- **No HTML from data.** `innerHTML` is never assigned anywhere in `site/src/lib/chat/`.

### `widget.ts`

```ts
export function mountChatWidget(opts?: { root?: ParentNode; send?: typeof sendChat; newSessionId?: () => string }): void;
```

Defaults are `root = document`, `send = sendChat`, and `newSessionId = () => crypto.randomUUID().replaceAll("-", "")`. The session id is created once per mount. If any required element id is missing, the function returns silently.

- **Counter.** On `input`, `#chat-count` shows `<len>/500`.
- **Roll toggle.** On `change` of `#chat-roll`, `#chat-modifier.disabled = !checked`.
- **Enter key.** Enter without Shift (and not during IME composition) in the textarea submits the form; Shift+Enter inserts a newline.
- **Submit.** `preventDefault`. While a request is pending, further submits are ignored. Then:
  1. Hide both field errors. If `message.trim()` is empty, show `EMPTY_MESSAGE` in `#chat-message-error`, focus the textarea and stop.
  2. If roll is checked and the modifier field is non-empty, it must parse as an integer in −10…10 (`Number.isInteger`). Otherwise show `MODIFIER_INVALID` in `#chat-modifier-error`, focus the field and stop.
  3. Append `renderUserMessage(message.trim())` to the log and clear the textarea (counter back to `0/500`).
  4. Disable the submit button, set its text to `Asking…`, and set `#chat-status` to `STATUS_START`.
  5. `await send({message: trimmed, roll, modifier: roll && field non-empty ? n : null, session_id}, {onStatus})`. `onStatus` sets `#chat-status` to `STATUS_BY_STEP[step]` when that key exists.
  6. On `reply`, append `renderReply`. On `failure`, append `renderFailure(message)`, and if the textarea is still empty, restore the sent message into it.
  7. Finally, clear `#chat-status`, re-enable the button (text `Ask`), call `scrollIntoView({block: "nearest"})` on the new item if available, and keep focus in the textarea.

## User-Facing Copy

**Backend** (`backend/api/messages.py`, exact; ASCII apostrophes):

| Constant | Code / status | Text |
|----------|---------------|------|
| `UNSUPPORTED_MEDIA_TYPE_TEXT` | `unsupported_media_type` 415 | `The request must be sent as JSON.` |
| `REQUEST_TOO_LARGE_TEXT` | `request_too_large` 413 | `The request was too large. Please send a shorter message.` |
| `INVALID_REQUEST_TEXT` | `invalid_request` 422 | `The request was not valid. Please reload the page and try again.` |
| `MESSAGE_TOO_LONG_TEXT` | `message_too_long` 422 | `Your message is too long. Please keep it to 500 characters or fewer.` (built from `MAX_MESSAGE_CHARS`) |
| `BUDGET_EXHAUSTED_TEXT` | `budget_exhausted` 503 | `The demo budget is used up for today. Please come back tomorrow. The rules pages still work in the meantime.` |
| `RATE_LIMIT_MINUTE_TEXT` | `rate_limited` 429, scope minute | `You're sending messages too quickly. Please wait a minute and try again.` |
| `RATE_LIMIT_DAY_TEXT` | `rate_limited` 429, scope day | `You've reached today's message limit for this demo. Please come back tomorrow.` |
| `TIMEOUT_TEXT` | SSE `error` `timeout` | `The assistant took too long to answer. Please try again.` |
| (spec 006 `ERROR_TEXT`) | SSE `error` `internal_error` | Imported from `backend.graph.replies`. |

**Widget** (`site/src/lib/chat/copy.ts`, exact):

| Constant | Text |
|----------|------|
| page intro (in `assistant.astro`) | `Ask a rules question, or describe what your character does and I'll tell you which move it triggers. Answers can be wrong: follow the links to check the rules.` |
| `STATUS_START` | `Reading your message…` |
| `STATUS_BY_STEP` | `router` → `Thinking…`; `retrieve` → `Writing an answer from the rules…`; `answer_with_citations` → `Checking the citations…`; `classify_move` → `Explaining the move…`; any other step leaves the status unchanged |
| `NETWORK_FAILURE` | `Couldn't reach the assistant. Check your connection and try again.` |
| `INTERRUPTED` | `The answer was interrupted. Please try again.` |
| `UNAVAILABLE` | `The assistant is unavailable right now. Please try again in a moment.` |
| `EMPTY_MESSAGE` | `Type a message first.` |
| `MODIFIER_INVALID` | `Enter a whole number from -10 to 10, or leave it empty.` |
| `SOURCES_TITLE` | `Sources` |
| `CLOSEST_TITLE` | `Closest sections in the rules` |
| `NOT_STATED` | `Not stated by this move.` (spec 004 D11) |
| `YOUR_ROLL` | ` (your roll)` |
| `NEW_TAB` | ` (opens in a new tab)` |

## Validation Rules

| Subject | Field / input | Rule | Failure |
|---------|---------------|------|---------|
| HTTP | `Content-Type` | Media type `application/json` (parameters allowed) | 415 |
| HTTP | body size | ≤ 16384 bytes (header and actual bytes) | 413 |
| `ChatRequest` | shape | JSON object; keys ⊆ {`message`, `roll`, `modifier`, `session_id`}; strict types (no coercion; `bool` is not an `int`; `1.0` is not an `int`) | 422 `invalid_request` |
| `ChatRequest` | `message` | Required `str`; stripped value non-empty | 422 `invalid_request` |
| `ChatRequest` | `message` | Stripped length ≤ 500 code points | 422 `message_too_long` |
| `ChatRequest` | `roll` | Optional `bool`, default `false` | 422 `invalid_request` |
| `ChatRequest` | `modifier` | Optional `int` or `null`, −10…10 | 422 `invalid_request` |
| `ChatRequest` | `session_id` | Optional; `^[0-9a-f]{32}$` | 422 `invalid_request` |
| Business | spend | `spent_today < CHAT_DAILY_BUDGET_USD` | 503 `budget_exhausted` |
| Business | rate | Per client: < per-day count today and < per-minute in the last 60 s | 429 `rate_limited` |
| `ApiSettings` | env | Ranges in *Configuration*; integers via `int()` on the stripped value; budget via `float()`, finite | `ConfigError` listing every problem as `<VAR> must be <rule>` |
| `SpendLedger.record` | `cost_usd` | Finite, ≥ 0 | `ValueError` |
| `sse_event` | `event` | `^[a-z_]+$` | `ValueError` |
| `NodeCompleted` | `node` | Non-empty `str` | `ValueError` |
| Widget | message | Trimmed non-empty; `maxlength` 500 | Inline `EMPTY_MESSAGE`; no request |
| Widget | modifier | Empty, or an integer −10…10; only sent when roll is checked | Inline `MODIFIER_INVALID`; no request |
| Widget | server payload | `replySchema`, including `url === sectionUrl(section_id)` / `moveUrl(move_id)`; `kind`, `stat`, `roll_stat`, `band` enums; `dice` a pair of integers 1–6 | Failure `malformed` |

## Authorization & Security

The API and site are public and anonymous by design (handoff 3: no login).

| Action | Who | Enforcement |
|--------|-----|-------------|
| `GET /api/health` | anyone | none |
| `POST /api/chat` | anyone, within limits | D8 guards: size, schema, length, global budget, per-IP rate |
| View `/assistant/` | anyone | static page |

- **Cost.** Every rejection happens before the graph runs, so no LLM call is made. `max_tokens` stays on every call (spec 006 D25, spec 007 D12). This is verified again through the API (`test_every_llm_request_has_max_tokens`). Other bounds: the daily cap (D12), the turn timeout (D13), and the in-memory-only limitation (D9, open risk a).
- **Cross-origin and CSRF.** The API requires `application/json` and sends no CORS headers. A browser cannot send such a POST cross-origin without a preflight, which fails, and other origins cannot read the responses. No cookies or credentials exist, so there is nothing to forge.
- **Injection.** The widget never assigns `innerHTML` and builds every `href` with `urls.ts` (D16). Server messages are rendered as text. Prompt injection is handled as in spec 006 (delimited user text, no tools).
- **Privacy.** See D11 and D17. No IP is traced, logged or stored raw. Run uvicorn with `--no-access-log`. The session id is random per page load and nothing is persisted in the browser.
- **Errors.** API responses never contain exception text. Internal details go only to the server log, with the trace id.

## Testing

**Backend.** pytest, plain functions, flat files in `backend/tests/` (spec 005 D15). HTTP tests use `fastapi.testclient.TestClient` as a context manager (runs the lifespan) over an app from `create_app(environ=..., runtime_factory=..., clock=FakeClock(...))`. From story 3 on, the app also gets `keyer=ClientKeyer(b"test-salt")`; `make_client` passes it once the parameter exists, and story 2's helpers and tests never reference `ClientKeyer` or `client_ip`. No test reads process env, and the spec 006 socket guard stays active.

**`backend/tests/api_helpers.py`**:
- `FakeClock(start=1_767_225_600.0)` (2026-01-01T00:00:00Z) with `advance(seconds)` and `__call__`.
- `runtime_factory(llm: LLMClient, *, retriever=FakeRetriever(), rng=ScriptedRandom([]), tracer=FakeTracer())` returns `(factory, state)`. The factory wraps `llm` in `MeteredLLMClient(llm, sink)` and builds `Runtime(build_assistant(GraphDeps(...)), close_callback)`. `state` records `closed: bool` and exposes the tracer.
- `make_client(llm, *, env=None, **kw)` returns `TestClient(create_app(environ=env or {}, ...))` (extra keyword arguments go to `runtime_factory` / `create_app`).
- `post_chat(client, body, *, headers=None)` sends JSON with `Content-Type: application/json`.
- `parse_sse(text) -> list[tuple[str, dict[str, object]]]`.
- `SlowLLMClient(delay_s)` sleeps with `asyncio.sleep`, then returns a router JSON.
- `CostLLMClient(inner, cost)` returns inner responses with `cost_usd` set.
- Reuses `graph_helpers.router_json`, `classifier_json`, `chunk`, `MOVES`, and `domain_helpers.ScriptedRandom`.

**`test_graph_stream.py`**
- `test_stream_yields_nodes_then_result`, parametrized over the five spec 006 tracing paths (out_of_scope, rules, move+roll, clarify, no_move). The `NodeCompleted` names equal the expected node lists from spec 006 `test_every_executed_node_is_traced`. The last event is a `TurnResult`, and it is the only one.
- `test_stream_result_equals_run_result`: for each path, two assistants with identical scripted fakes give `stream`'s `TurnResult == run`'s.
- `test_stream_error_reply_still_completes`: a router `PortError` yields `NodeCompleted("router")`, then a `TurnResult` with kind `error`.
- `test_stream_without_reply_raises`: `_assistant_from_compiled` over a graph returning `{}` raises `RuntimeError("graph finished without a reply")` while iterating.
- `test_node_completed_validation`: an empty `node` raises `ValueError`.

**`test_adapters_metered_llm.py`**
- `test_records_provider_cost`: an inner response with `cost_usd=0.002` calls `on_cost` with `[0.002]`, and the returned response `is` the inner one.
- `test_missing_cost_counts_fallback_and_warns_once`: two calls with `cost_usd=None` give `[0.01, 0.01]` and exactly one WARNING (`caplog`).
- `test_port_error_records_nothing`: the inner client raises `PortError`, which propagates, and `on_cost` is never called.
- `test_request_passed_through_unchanged`: the inner `FakeLLMClient.requests[0] is request`.
- `test_satisfies_llm_client_protocol`: annotated assignment.

**`test_composition.py`** (additive)
- `test_build_runtime_meters_llm_cost`: the spec 007 `test_end_to_end_rules_turn_with_real_adapters` setup (mock transport, `cost=0.00042`) with `on_llm_cost=costs.append`. After the turn, `costs == [0.00042, 0.00042]` (router and answer).

**`test_api_settings.py`**
- `test_defaults_when_unset`: `{}` gives `5, 50, 1.0, 0`.
- `test_valid_values_parsed`: `" 7 "` is stripped to 7, and `"2.50"` gives 2.5.
- `test_invalid_values_listed_together`: `CHAT_RATE_PER_MINUTE="x"`, `CHAT_DAILY_BUDGET_USD="0"` and `CHAT_TRUSTED_PROXY_HOPS="9"` give one `ConfigError` naming all three.
- `test_budget_rejects_nan_and_inf`.
- `test_env_example_declares_api_settings`: every name in `API_ENV_VARS` is a key in `.env.example`.

**`test_api_limits.py`** (unit; `FakeClock`)
- `test_minute_limit_allows_then_rejects`: with `per_minute=2`, two calls are allowed and the third returns `scope "minute"` with `retry_after_s == 60`.
- `test_minute_window_slides`: after `advance(30)` and one more call at the limit, `retry_after_s == 30`. After `advance(31)`, the call is allowed.
- `test_day_limit_rejects_until_midnight`: with `per_day=3` and `per_minute=100`, the fourth call returns `scope "day"`, and `retry_after_s == seconds_until_utc_midnight(now)`.
- `test_day_resets_at_utc_midnight`: advancing past midnight allows the next call.
- `test_rejected_requests_not_counted`: after a minute rejection and `advance(60)`, exactly `per_minute` calls are allowed again.
- `test_keys_are_independent`: with `per_minute=1`, key `"a"` is allowed once and then rejected (`scope "minute"`), while key `"b"` is still allowed on its first call at the same instant.
- `test_least_recent_client_evicted`: with `max_clients=2`, keys a, b, c leave a forgotten (a's next call starts fresh).
- `test_seconds_until_utc_midnight`: 23:59:59.5Z gives 1, and 00:00:00Z gives 86400.
- `test_spend_ledger_accumulates_and_exhausts`: with cap 0.05, 0.02 + 0.02 is not exhausted, and a further + 0.01 is exhausted (`>=`).
- `test_spend_ledger_resets_next_utc_day`.
- `test_spend_ledger_rejects_invalid_cost`: −0.01 and `nan` raise `ValueError`.
- `test_client_ip_cases`, parametrized:
  - hops 0 returns the peer.
  - hops 1 with `"1.1.1.1, 2.2.2.2"` returns `"2.2.2.2"`.
  - hops 2 returns `"1.1.1.1"`.
  - hops 1 without the header returns the peer.
  - hops 3 with two entries returns the peer.
  - A peer of `None` gives `"unknown"`.
  - The header name is matched case-insensitively.
- `test_client_keyer_hides_ip`: the key is 32 hex characters, differs from the IP, is stable for the same salt and differs for another salt.

**`test_api_sse.py`**
- `test_frame_format`: `sse_event("status", {"step": "router"}) == b'event: status\ndata: {"step":"router"}\n\n'`.
- `test_newlines_in_data_are_escaped`: text containing `"a\n\nb"` gives exactly one `data:` line.
- `test_non_ascii_preserved`: `"’"` is UTF-8 encoded, not `’`.
- `test_invalid_event_name_rejected`: `"bad name"` raises `ValueError`.

**`test_api_contract.py`**
- `test_reply_payload_matches_fixture`, parametrized over the four fixture keys. The test constructs the matching `TurnResult` directly (spec 005/006 types: `Reply`, `Citation`, `MoveCard`, `Outcomes`, `Roll`, `Outcome`), using the fixture's `trace_id`. `reply_payload(...)` equals `json.loads(fixture)[key]`, including key order (`list(payload) == list(expected)`).
- `test_fixture_urls_follow_url_contract`: every citation `url == section_url(section_id)` and every move `url == move_url(move_id)`.
- `test_reply_payload_is_json_serialisable_for_every_kind`: one minimal `Reply` per `ReplyKind` gives a `json.dumps` that does not fail.

**`test_api_chat.py`** (happy paths and failures after streaming)
- `test_health_ok`: 200, `{"status": "ok"}`, `Cache-Control: no-store`.
- `test_rules_question_streams_status_then_reply`: router `rules_question`, one chunk, answer citing it. 200, with `Content-Type` starting with `text/event-stream` and `Cache-Control: no-store`. The events are `status` router, retrieve, answer_with_citations, citation_validator, then `reply`. The reply has kind `rules_answer`, a citation url of `/rules/moves/hack-and-slash/`, and a `trace_id` matching `^[0-9a-f]{32}$`.
- `test_move_turn_with_roll_and_modifier`: classifier `hack-and-slash` 0.9, body `{"roll": true, "modifier": 1}`, `ScriptedRandom([4, 5])`. `reply.move.roll == {"dice": [4, 5], "modifier": 1, "total": 10}` and `reply.move.outcome.band == "strong_hit"`.
- `test_out_of_scope_turn`: the events are `status` router, `status` out_of_scope, then `reply` kind `out_of_scope`.
- `test_graph_error_is_reply_event`: a router `PortError` gives a `reply` with kind `error` and spec 006's `ERROR_TEXT`, and no `error` event.
- `test_unexpected_exception_emits_error_event`: a runtime whose `assistant.stream` raises `RuntimeError("boom")` after one `NodeCompleted` gives events `status`, then `error` `{"code": "internal_error", "message": ERROR_TEXT}`. The ERROR log contains `RuntimeError` and the trace id, and does not contain the user message.
- `test_turn_timeout_emits_error_event`: `create_app(..., turn_timeout_s=0.05)` with `SlowLLMClient(1.0)`. The last event is `error` with code `timeout` and `TIMEOUT_TEXT`.
- `test_session_id_passed_through`: the body `session_id` of `"ab" * 16` is the `session_id` of every `FakeTracer` record.
- `test_session_id_generated_when_absent`: the tracer records a 32-hex session id.
- `test_trace_id_fresh_per_request`: two requests have different `trace_id`s, and each equals the tracer's `trace_id` for its turn.
- `test_message_stripped_before_graph`: `"  hi  "` makes the router request `user` contain `<user_message>\nhi\n</user_message>`.
- `test_every_llm_request_has_max_tokens`: the rules and move+roll turns give `FakeLLMClient.requests` whose `max_tokens` are exactly `[100, 700]` and `[100, 400, 300]`.
- `test_runtime_closed_on_shutdown`: after the `TestClient` context exits, `state.closed is True`.
- `test_create_app_rejects_invalid_settings`: `CHAT_RATE_PER_MINUTE="0"` makes `create_app` raise `ConfigError`.
- `test_default_factory_fails_fast_without_config`: `create_app(environ={})` (no runtime factory) succeeds, but entering `TestClient` raises `ConfigError` naming `OPENROUTER_API_KEY`.

**`test_api_validation.py`** (each case also asserts that `FakeLLMClient.requests == []` and that the error body shape and `Cache-Control: no-store` are present)
- `test_wrong_content_type_415`: `text/plain`.
- `test_body_too_large_413`: a 20,000-byte JSON body.
- `test_invalid_request_422`, parametrized:
  - not JSON
  - `[]`
  - `{}`
  - `{"message": 5}`
  - `{"message": "hi", "extra": 1}`
  - `{"message": "hi", "roll": "true"}`
  - `{"message": "hi", "modifier": 11}`
  - `{"message": "hi", "modifier": true}`
  - `{"message": "hi", "modifier": 1.5}`
  - `{"message": "hi", "session_id": "XYZ"}`
  - `{"message": "   "}`

  Each gives 422 with code `invalid_request` and `INVALID_REQUEST_TEXT`.
- `test_message_too_long_422`: 501 `"a"`s gives `message_too_long` with `MESSAGE_TOO_LONG_TEXT`.
- `test_message_at_limit_accepted`: 500 `"a"`s surrounded by spaces gives 200.
- `test_non_ascii_length_counts_code_points`: 500 × `"é"` (1,000 UTF-8 bytes) gives 200.
- `test_invalid_requests_do_not_consume_rate_limit`: with `CHAT_RATE_PER_MINUTE=1`, three invalid requests followed by one valid request gives 200.

**`test_api_guardrails.py`**
- `test_rate_limit_per_minute_429`: with `CHAT_RATE_PER_MINUTE=2`, the third request gets 429 `rate_limited` with `RATE_LIMIT_MINUTE_TEXT` and `Retry-After: 60`. Router requests total exactly 2.
- `test_rate_limit_resets_after_window`: after `clock.advance(61)`, the request gets 200.
- `test_rate_limit_daily_429`: with `CHAT_RATE_PER_DAY=2` and `CHAT_RATE_PER_MINUTE=100`, the third request gets 429 with `RATE_LIMIT_DAY_TEXT` and `Retry-After` equal to the seconds to midnight.
- `test_rate_limit_keyed_by_forwarded_ip`: with hops 1, two requests from `X-Forwarded-For: 9.9.9.9, 1.1.1.1` and one from `9.9.9.9, 2.2.2.2` under `CHAT_RATE_PER_MINUTE=2` all get 200. A third from `…, 1.1.1.1` gets 429, including when its spoofed leftmost entry changes.
- `test_rate_limit_ignores_forwarded_header_by_default`: with hops 0, two different `X-Forwarded-For` values share the `testclient` peer bucket.
- `test_budget_exhausted_503`: with `CHAT_DAILY_BUDGET_USD=0.01` and the fake LLM's `cost_usd=None` (fallback 0.01), the first out_of_scope turn gets 200. The second gets 503 `budget_exhausted` with `BUDGET_EXHAUSTED_TEXT` and a `Retry-After`, and the router requests total 1.
- `test_budget_counts_reported_cost`: with `CostLLMClient(cost=0.004)`, `CHAT_DAILY_BUDGET_USD=0.01` and rules turns (2 calls = 0.008), the second turn is allowed (0.008 < 0.01) and the third is rejected (0.016 ≥ 0.01).
- `test_budget_resets_next_utc_day`: after `clock.advance` past midnight, the request gets 200.
- `test_budget_rejection_does_not_consume_rate_limit`: with `CHAT_DAILY_BUDGET_USD=0.01` and `CHAT_RATE_PER_MINUTE=2`, the first turn gets 200 (budget now exhausted) and the next three requests get 503. After `clock.advance` past the next UTC midnight (which resets the budget, while the minute window of the first turn has also expired), two requests get 200 and the third gets 429. This shows the 503s did not count against the rate limit.
- `test_health_ok_when_budget_exhausted`: after the budget is exhausted as in `test_budget_exhausted_503`, `GET /api/health` gets 200 `{"status": "ok"}` and the router request count is still 1.
- `test_no_ip_in_traces_or_logs`: with `CHAT_TRUSTED_PROXY_HOPS=1` and `X-Forwarded-For: 203.0.113.7`, one rules turn and one 429 rejection (`CHAT_RATE_PER_MINUTE=1`) leave `"203.0.113.7"` in no `FakeTracer` node, generation or event (ids and attribute values) and in no captured log record at any level.

**`test_api_layering.py`** (AST scan, spec 005 D13 style)
- `test_api_imports_allow_list`: `backend/api/*.py` imports only the stdlib, `fastapi`, `starlette`, `pydantic`, `backend.api.*`, `backend.graph.builder`, `backend.graph.state`, `backend.graph.replies`, `backend.ports.*`, `backend.domain.*` and `backend.composition`. The test asserts that `app.py` was scanned.
- `test_web_framework_confined_to_api`: no file under `backend/domain`, `backend/ports`, `backend/graph` or `backend/adapters`, and not `backend/composition.py`, imports `fastapi`, `starlette` or `backend.api`.

**Frontend.** Vitest (spec 004 D7). Pure modules use the `node` environment. `chat-render.test.ts` and `chat-widget.test.ts` start with `// @vitest-environment happy-dom`. Fixtures come from `backend/tests/fixtures/chat_reply_examples.json`, read with `fs.readFileSync(new URL("../../../backend/tests/fixtures/chat_reply_examples.json", import.meta.url))`. Fake fetch responses are built with `new Response(new ReadableStream(...), {headers: {"Content-Type": "text/event-stream"}})`, enqueuing the chunks given in the test.

**`tests/unit/chat-sse.test.ts`**
- `parses named events`: `event: status\ndata: {"step":"router"}\n\n` gives one message.
- `joins multi-line data`.
- `handles CRLF and CR line endings`.
- `handles events and line endings split across chunks`: the same stream fed byte by byte gives the same messages.
- `ignores comments and unknown fields`.
- `strips one leading space only`.
- `defaults event name to message`.
- `drops an unterminated final event`.
- `readSse decodes multi-byte characters split across chunks`: `’` split between two `Uint8Array` chunks.

**`tests/unit/chat-protocol.test.ts`**
- `accepts every fixture reply`.
- `rejects a citation url that differs from sectionUrl`: `url: "javascript:alert(1)"`.
- `rejects a move url that differs from moveUrl`.
- `rejects an unknown kind`.
- `rejects dice outside 1-6`.
- `strips unknown keys`: an extra `intent` key parses, and the key is absent from the output.
- `parses http error bodies`: `{"error": {"code": "rate_limited", "message": "Slow down."}}` parses to that object. `{"error": {"code": "x"}}` (no message) and `{"detail": "Not Found"}` fail to parse.

**`tests/unit/chat-client.test.ts`**
- `posts the request body as json with sse accept header`: the fake fetch captures the URL `/api/chat`, method `POST`, both headers and the exact JSON body.
- `reports status steps then returns the reply`: `onStatus` is called with `["router", "retrieve"]` and the outcome is `reply`, equal to the fixture.
- `ignores unknown events`: a `delta` event before `reply` still gives `reply`.
- `maps an error event to a failure`.
- `maps http error bodies`: 429 with a JSON body gives a failure with code `rate_limited` and the server message. 503 gives `budget_exhausted`.
- `falls back when the error body is not json`: a 502 HTML body gives failure `http_502` with `UNAVAILABLE`.
- `maps network errors`: fetch rejects with `TypeError`, giving `network` with `NETWORK_FAILURE`.
- `fails when the stream ends without a reply`: `interrupted`.
- `fails on malformed reply json`: `malformed`.
- `fails on a non sse response`: 200 `application/json` gives `malformed`.
- `MAX_MESSAGE_CHARS is 500`.

**`tests/unit/chat-render.test.ts`** (happy-dom)
- `segments markers into numbered citations`: for the fixture `rules_answer`, the segments are text, citation 1, text, citation 2, text.
- `drops markers that are not citations`.
- `renders paragraphs and citation links`: `rules_answer` gives two `<p>`. The links have `href` `/rules/moves/hack-and-slash/` and `/rules/moves/defy-danger/`, text `[1]`/`[2]`, `target="_blank"`, `rel="noopener noreferrer"`, and an `aria-label` starting with `Source 1: Hack and Slash`.
- `renders a sources list titled Sources`.
- `titles not-found citations as closest sections`.
- `renders the move card with roll and result band`: for `move_rolled_with_modifier`, the card heading link is `/moves/hack-and-slash/` and the `Roll` dd is `+STR`. The `Dice` dd is `4 + 5 + 1 = 10`. The `is-result` dt is `10+ (strong hit) (your roll)`, and the miss dd is `Not stated by this move.`.
- `renders a roll without modifier`: for `move_rolled_without_modifier`, `Roll` is `+stat chosen by how you act`, `Dice` is `3 + 5 = 8, before your modifier`, and there is no `is-result`.
- `renders no outcomes block for a non-rolled move`: a payload with `outcomes: null, roll: null` gives no `.outcomes`, and `Roll` is `Not rolled`.
- `escapes html in all text`: `text` `<img src=x onerror=alert(1)>` and a title containing `<b>` produce no `img`/`b` element, and the text is shown literally.
- `marks error replies`: kind `error` gives class `chat-error` and an `Error: ` prefix.
- `diceText formats negative modifiers`: `3 + 3 - 1 = 5`.

**`tests/unit/chat-widget.test.ts`** (happy-dom). The body is set to the component markup (the same ids as *Page and component*), and the test mounts with a fake `send` and `newSessionId: () => "ab".repeat(16)`.
- `sends the trimmed message with session id`: `send` gets `{message: "hi", roll: false, modifier: null, session_id: "abab…"}`. The log gets a user item and a reply item.
- `blocks an empty message`: `"   "` makes no call, and `EMPTY_MESSAGE` is visible.
- `modifier enabled only when roll is checked`.
- `sends the modifier only when rolling`: roll checked with `-2` gives `modifier: -2`. With roll unchecked, the field is disabled and `modifier: null` is sent.
- `rejects an invalid modifier`: `11` makes no call and shows `MODIFIER_INVALID`.
- `shows progress and disables the button while pending`: the fake `send` returns a promise the test resolves manually and captures `opts.onStatus`. After submitting `"hi"`:
  - `#chat-submit` has `disabled === true` and `textContent === "Asking…"`, and `#chat-status` has `textContent === "Reading your message…"`.
  - After calling the captured `onStatus("retrieve")`, `#chat-status` is `Writing an answer from the rules…`.
  - After calling `onStatus("citation_validator")`, the status is unchanged.
  - After resolving with the fixture `rules_answer` and awaiting a microtask flush, `#chat-status` is `""`, `#chat-submit` has `disabled === false` and `textContent === "Ask"`, and `#chat-log` has 2 `li` children.
- `ignores a second submit while pending`.
- `renders a failure and restores the message`: a failure outcome adds a `chat-error` item, and the textarea again contains the message.
- `enter submits and shift enter does not`.
- `updates the character counter`.
- `uses a fresh session id per mount only`: two submits send the same id.

**`tests/unit/format.test.ts`** (additive)
- `bandLabel maps every band`.

**`tests/dist/site.test.ts`** (additive)
- `assistant page renders the chat widget`: `dist/assistant/index.html` contains `id="chat-form"`, `maxlength="500"`, `role="log"`, `role="status"`, `<label for="chat-message">` and a `<script type="module"`.
- `header links the assistant on every page`: every HTML file contains `href="/assistant/"`.

**Manual / CI:**
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` and `uv run pytest` exit 0.
- In `site/`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` and `npm run check-links` exit 0.

## Documentation

- **ADR "Chat API: SSE protocol, guardrails and in-memory limits"** (content from D1–D5, D7–D14, D17, D18). It must include:
  - The event table and the reason there is no token streaming (D2).
  - The guard order.
  - The default limits and budget, and the fallback cost.
  - The per-process limitation, with the three mitigations (D9, open risk a).
  - The trusted-hops rule.
  - The dependency justifications.
- **ADR "Chat widget: vanilla island on /assistant/, same-origin fetch"** (content from D6, D15, D16, D19). It must state:
  - Why not `EventSource`.
  - Why not a UI framework.
  - Why a dedicated page with new-tab links.
  - The rendering safety rules.
- **`docs/architecture.md`**: append `## API and chat widget`, containing the diagram from *Architecture / Design Overview* and a one-line description per module in `backend/api/` and `site/src/lib/chat/`.
- **`README.md`**: under `## Development`, add `### Running the API and chat widget locally`:
  - Configure `.env` as in "Running the assistant locally" (spec 007). The four `CHAT_*` keys are optional.
  - Start the API: `uv run --env-file .env uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`, with a single worker (the limits are in-memory).
  - In `site/`, run `npm run dev` and open `http://localhost:4321/assistant/`. Requests to `/api` are proxied to port 8000.
  - Health check: `curl http://127.0.0.1:8000/api/health`.

## Suggested Story Breakdown

The spec splits into backend stories for `python-feature-builder` and frontend stories for `astro-feature-builder` (spec 003). Each story is closed through its own `run-stage` review gate.

1. **[backend] Graph streaming and cost metering.** `NodeCompleted`, `Assistant.stream`, `MeteredLLMClient`, the `build_runtime(on_llm_cost=...)` hook. Tests: `test_graph_stream.py`, `test_adapters_metered_llm.py`, the `test_composition.py` addition. Verifiable on its own: the stream equals `run` on every path. Depends on specs 006 and 007.
2. **[backend] Chat API core.** Add `fastapi` and `uvicorn`. `settings.py`, `schemas.py`, `sse.py`, `messages.py`, `app.py` with health, the content-type/size/schema/length guards and SSE streaming (no limits yet). The contract fixture, `api_helpers.py`, `test_api_settings.py`, `test_api_sse.py`, `test_api_contract.py`, `test_api_chat.py`, `test_api_validation.py` (without the rate-limit case), `test_api_layering.py`, and the `.env.example` keys. Verifiable with curl against a local uvicorn. Depends on 1.
3. **[backend] Guardrails: rate limit and spend cap.** `limits.py` (including `client_ip` and `ClientKeyer`), guards 6–7 in `app.py`. This story adds the `keyer` parameter of `create_app` and passes it from `make_client`. It also wires the ledger to the runtime factory (story 2 passes a no-op sink). Tests: `test_api_limits.py`, `test_api_guardrails.py` (including `test_no_ip_in_traces_or_logs`), the remaining validation case, the API ADR, and the README and architecture sections for the API. Depends on 2.
4. **[frontend] Chat client library.** `happy-dom`, `sse.ts`, `protocol.ts`, `client.ts`, `copy.ts`, `render.ts`, `bandLabel`, and their unit tests (they read the story 2 fixture). Verifiable with `npm test`. Depends on story 2 (the fixture) and spec 004.
5. **[frontend] Widget page and end-to-end.** `widget.ts`, `ChatWidget.astro`, `assistant.astro`, `ASSISTANT_URL`, the header link, CSS, the dev proxy, `chat-widget.test.ts`, the dist tests, the widget ADR and the README widget lines. Then the owner's manual end-to-end check (*Success Criteria*). Depends on 3 and 4.

## Success Criteria

Automated:
- [ ] Every backend test in *Testing* exists and passes with `uv run pytest`, with no env vars set and no network. Every spec 006 and 007 test passes unmodified, apart from the one additive `test_composition.py` case.
- [ ] `uv run ruff format --check .`, `uv run ruff check .` and `uv run pyright` exit 0.
- [ ] `[project].dependencies` gains exactly `fastapi` and `uvicorn`, and `uv sync --locked` succeeds.
- [ ] Every frontend test in *Testing* exists and passes. `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` and `npm run check-links` exit 0 in `site/`, and `happy-dom` is the only new site dependency.
- [ ] `test_api_validation.py` and `test_api_guardrails.py` prove that oversized, invalid, rate-limited and over-budget requests make zero LLM calls.
- [ ] `test_no_ip_in_traces_or_logs` and `test_every_llm_request_has_max_tokens` pass.
- [ ] `test_reply_payload_matches_fixture` and `accepts every fixture reply` pass against the same fixture file.
- [ ] `grep -rn "innerHTML" site/src/lib/chat` finds nothing. `grep -rn '"/rules/\|"/moves/' site/src` still finds only `urls.ts`.
- [ ] `docs/decisions.md` has both ADRs. `docs/architecture.md` and `README.md` have the new sections, and `.env.example` has the four keys.

Owner verification (real keys; milestone 7 acceptance):
- [ ] With the API and `npm run dev` running, asking "How does Hack and Slash work?" on `/assistant/` shows progress messages, then an answer with numbered citation links. Those links open the matching `/rules/…/` pages.
- [ ] "I swing my sword at the goblin" with "Roll the dice for me" and modifier `1` shows a move card with name, `+STR`, three bands, the dice line, and the rolled band marked "(your roll)".
- [ ] A 501-character message sent with curl gets 422 `message_too_long`. With `CHAT_RATE_PER_MINUTE=1`, a second quick question shows the "too quickly" message in the widget. With `CHAT_DAILY_BUDGET_USD=0.0001`, the second question shows the budget message.
- [ ] Langfuse shows the widget's turns under one session id, and no IP address appears in any trace.

## Future Considerations

- Token streaming (`delta` events): stream the prose of the rules answer while holding back `[[…]]` markers until validated, through a streaming method on `LLMClient`. Old widgets keep working because they ignore unknown events.
- Shared rate-limit and spend state (Firestore or Redis) so the limits survive restarts and multiple Cloud Run instances.
- An "Ask about this section" link on rules pages that opens `/assistant/` with a prefilled question.
- Persisting the transcript in `sessionStorage` so same-tab navigation keeps the conversation.
- Exposing remaining-budget information in `/api/health` for monitoring, if spec 011 needs it.
- A cancel button that aborts the in-flight request (`AbortController` is already supported by `sendChat`).
