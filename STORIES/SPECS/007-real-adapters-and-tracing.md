# 007 - Real adapters, retrieval index, and tracing

**Status:** spec — ready for story-creator.
**Depends on:** 001 (toolchain, `backend/adapters/` package, `.env.example` convention, `docs/`), 002 (`data/normalized/sections.json` / `moves.json` shapes and IDs), 004 (URL contract D1), 005 (`Move`, `Section`, `move_from_dict`, `section_from_dict`), 006 (ports, fakes, graph, `GraphDeps`, `build_assistant`, `backend/domain/urls.py`, no-network test guard).
**Reference:** `HANDOFF_dw-companion.md` sections 4.1, 4.2, 4.3, 7, 8, 10 (milestone 6), 12.

## Feature Name & Description

**Real adapters and the composition root.** Replace spec 006's fakes in production with real implementations of the four ports: an OpenRouter `LLMClient`, a hybrid (vector + BM25) `Retriever` over an offline-built index, a Langfuse `Tracer`, and a JSON `RulebookRepository`. A composition root reads environment variables and wires them into the spec 006 graph. A local chat command lets you run a turn end to end. The value is milestone 6: the assistant answers real questions, and every turn shows up in Langfuse with model, tokens, cost, latency and intent.

**Current state.** Nothing is implemented yet; specs 001, 002, 004, 005 and 006 are approved but not built. Paths marked "(new in 00N)" come from those specs and do not exist on disk yet. Spec 006 defines the ports and the graph against fakes; no adapter, index or composition root exists.

**In scope.**
- OpenRouter chat adapter, plus an OpenRouter embeddings client.
- Section/move chunking, an index build CLI and a committed index artifact.
- BM25 and the hybrid retriever.
- Langfuse tracer and a no-op tracer.
- JSON rulebook repository.
- Composition root (`Settings.from_env`, `build_runtime`) and the `python -m backend.chat` CLI.
- One additive field on `LLMResponse` (`cost_usd`).
- New dependencies `openai`, `langfuse`, `numpy`.
- `.env.example` keys, three ADRs, an architecture doc section and a README subsection.

**Out of scope.**
- The FastAPI app, SSE, rate limits, input limits and spend cap (spec 008).
- Eval datasets, retrieval or answer quality measurement, and model selection (specs 009/010).
- The Dockerfile and Secret Manager wiring (spec 011). This spec produces the artifact spec 011 copies into the image.
- Token streaming, conversation memory and class moves (spec 006 out of scope).

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Embeddings come from OpenRouter too, with the same key and SDK. The draft's premise is outdated.** Verified on 2026-11-05: `GET https://openrouter.ai/api/v1/models?output_modalities=embeddings` lists 44 embedding models, including `openai/text-embedding-3-small` at $0.02 per million input tokens. `POST https://openrouter.ai/api/v1/embeddings` answers 401 (the route exists), while an unknown route answers 404. `MODEL_EMBEDDINGS` is therefore an OpenRouter model id. **Owner review item #1.** To override with a direct OpenAI key instead, add `EMBEDDINGS_API_KEY`/`EMBEDDINGS_BASE_URL` and build a second `AsyncOpenAI` client in `backend/composition.py`. The embedder takes an injected client, so no adapter changes. **Stories proceed on this default (OpenRouter embeddings) without waiting for the review.** | Handoff 12 ("boring libraries, justify every dependency"; "stop and ask … recurring cost beyond free tiers"). This option adds zero dependencies, no second account, no second secret and no second billing alert, versus a direct OpenAI key. It also avoids a local model (`fastembed` + `onnxruntime`, which adds about 150 MB to the image and Cloud Run cold-start load time; handoff 8 `min-instances=0`). Cost (handoff 7): a full index build is under $0.05. A query embedding (~30 tokens) costs about $0.0000006. |
| D2 | **Embedding model for the committed index: `openai/text-embedding-3-small`.** It is not hardcoded: it is the value of `MODEL_EMBEDDINGS` when the index is built, and it is recorded in the index manifest. At startup the composition root refuses to run if `MODEL_EMBEDDINGS` differs from the manifest. | Cheapest well-known general embedding model with an 8,192-token context. Query and index vectors must come from the same model, so a mismatch fails fast instead of returning garbage rankings. Changing it is a spec 010 decision followed by an index rebuild. |
| D3 | **Vector store: a NumPy matrix (`embeddings.npy`, float32, L2-normalised rows) plus brute-force cosine similarity.** No Chroma, LanceDB or FAISS. New dependency `numpy`. PR line: *"NumPy stores and scores the ~400-vector embedding matrix; it is the standard array library and needs no server."* | The corpus is one book (a few hundred chunks × 1,536 dims, about 2–3 MB). A matrix-vector product costs well under a millisecond. Chroma pulls a SQLite stack and its own embedding runtime; LanceDB pulls `pyarrow`; FAISS is built for millions of vectors. Handoff 4.3 [decided]: no managed vector DB. |
| D4 | **The index artifact is committed to git under `data/index/`** and rebuilt by a CLI (`python -m backend.adapters.retrieval.build`) that needs `OPENROUTER_API_KEY`. Spec 011's Dockerfile `COPY`s it into the image. A test fails when `chunks.json` no longer matches the chunks derived from the committed normalized data. | Same precedent as spec 002 D13 (committed `data/normalized/`). It keeps "built offline, baked into the image" (handoff 4.3/8) without a secret in the Docker build. CI never calls a paid API (handoff 6.4). Index changes are visible in diffs. |
| D5 | **BM25 is implemented in-house** (`bm25.py`: Okapi BM25 with `k1=1.2`, `b=0.75`, non-negative IDF `ln(1 + (N − df + 0.5)/(df + 0.5))`). It is built in memory at startup from the chunk texts and never persisted. No BM25 library. | `rank-bm25` is the well-known option, but its last release was 2022-02, it is untyped (noise under pyright strict, spec 001 D1), and it needs our tokenizer anyway. `bm25s` adds `scipy`. The formula is about 40 lines and fully unit-testable. Building it for ~400 short documents takes milliseconds. |
| D6 | **Tokenizer for BM25:** NFKC-normalise, lower-case, take tokens with `re.findall(r"[a-z0-9]+", text)`. No stemming and no stop-word list; IDF down-weights common words. | Exact game terms ("hack and slash", "last breath", "hold") are why handoff 4.3 asks for keyword search. Stemming could merge distinct terms; IDF already handles "and"/"the". Stemming is a spec 010 option if evals show misses. |
| D7 | **Fusion: Reciprocal Rank Fusion** of the top 30 vector hits and the top 30 BM25 hits (BM25 hits = score > 0). `score = Σ 1/(60 + rank)`, ranks 1-based. Ties are broken by chunk order. Results are deduplicated by `section_id` (first wins), then cut to `k`. `RetrievedChunk.score` is the RRF score. | RRF needs no score normalisation between cosine and BM25 scales and is the standard simple hybrid. Dedup enforces the spec 006 `Retriever` contract (distinct `section_id`, at most `k`, most relevant first). |
| D8 | **Chunking (handoff 4.3).** One chunk per section with non-empty `text_markdown`, with three exceptions: (a) sections whose id is a move's `section_id` are replaced by that move's chunk (`type="move"`), which resolves spec 002 open risk (b) by indexing each basic/special move exactly once; (b) chapter `thanks` (backer lists, spec 002 D18 left this filter to spec 007) is excluded; (c) a section longer than `MAX_CHUNK_CHARS = 6000` is split into parts packed greedily from whole Markdown blocks (blank-line separated), never mid-block. Move chunks are never split, whatever their length. Every part keeps its section's `section_id`, `title`, `chapter` and `anchor_url`. | Sections are the semantic unit (spec 002 D4: chapter → h1 → h2). The size cap keeps the rules prompt bounded: k=6 chunks × ~1.5k tokens, matching handoff 7 cost guardrails. Splitting only at block boundaries keeps chunks semantic, not fixed token windows. Section sizes at the pin are unmeasured, so the constant is tunable (spec 010). |
| D9 | **`anchor_url = section_url(section_id)`** (`/rules/<section_id>/`, spec 006 `backend/domain/urls.py`) for every chunk, moves included. `chapter` = the chapter id (spec 002 `Section.chapter`). | Spec 004 D1/ADR-009 citation contract. Spec 004's Future Considerations asks spec 007 for a Python-side test of this formula. Citations point at the rules section; the move card's `/moves/<id>/` link comes from spec 006's `MoveCard.url`. |
| D10 | **Index text** (what is embedded and BM25-indexed) = `"{chapter title} > {title}\n\n{text}"`, where chapter title = title of the section whose id equals the chapter (for that root section itself: `"{title}\n\n{text}"`). Embedding input is truncated to `EMBED_MAX_CHARS = 24000` characters, which only an oversized single block can reach; the build prints a warning per truncated chunk. `RetrievedChunk.text` is the raw part text without the header. | The header gives short sections context ("The Fighter > Bend Bars, Lift Gates"). 24,000 characters stays under the model's 8,192-token limit. The prompt shows the title separately (spec 006 `rules_user`). |
| D11 | **`LLMResponse` gains one additive optional field `cost_usd: float \| None = None`** in `backend/ports/llm.py`. The OpenRouter adapter fills it from the provider-reported `usage.cost`; the Langfuse tracer sends it as `cost_details`. Protocol signatures (`LLMClient.generate`, `Tracer.*`) are unchanged. Existing constructions, `FakeLLMClient` and all spec 006 tests keep working through the default. | Milestone 6 needs cost, and spec 006's `LLMResponse` has no cost field. The alternatives were worse: a Langfuse-side price table means manual per-model setup that drifts from real prices; a subclass side channel couples the tracer to the LLM adapter. OpenRouter's reported cost is the billed truth. Spec 009 can read cost from `GenerationTrace` with no further change. |
| D12 | **OpenRouter chat requests** use the `openai` SDK (`AsyncOpenAI`, `base_url="https://openrouter.ai/api/v1"`). Structured requests send `response_format={"type": "json_schema", "json_schema": {"name", "strict": true, "schema"}}` and `provider.require_parameters = true`, so OpenRouter only routes to providers that honour the schema. Every request sends `usage.include = true`. Timeout 30 s, `max_retries=1` (SDK transport retries on connection errors, 429 and 5xx). New dependency `openai`. PR line: *"Official OpenAI-compatible SDK; OpenRouter's documented client for chat and embeddings; typed and async."* | Handoff 4.2 (structured output, temperature 0 for router/classifier, `max_tokens` on every call: spec 006 sets them in `LLMRequest`). `python-feature-builder` requires a timeout on every outbound call. One transport retry bounds latency; the graph itself never retries (spec 006 D5). |
| D13 | **Model ids come only from env**: `MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER`, `MODEL_EMBEDDINGS`, all required. `.env.example` keeps empty values (spec 001 rule). Suggested starting values for local smoke runs are recorded in the provider ADR, not in code, marked provisional until spec 010: router/classifier `openai/gpt-4.1-nano`, answer `openai/gpt-4.1-mini`, embeddings `openai/text-embedding-3-small`. All were listed on OpenRouter on 2026-11-05 with `structured_outputs` support for the chat models. Non-reasoning models are suggested because reasoning tokens count against the small `max_tokens` budgets. | Handoff 4.2: "never hardcode"; model choice with eval evidence is spec 010's. A developer still needs working values to run milestone 6. |
| D14 | **Langfuse via the official SDK (`langfuse`, 5.x, OpenTelemetry-based).** New dependency `langfuse`. PR line: *"Official Langfuse client; batches and exports traces on a background thread, which is how the Tracer port's never-block contract is met."* Each `record_*` call creates one observation, attached to the Langfuse trace derived from `trace_id`, and ends it immediately. Export is asynchronous (the SDK's batch span processor). Every SDK call is wrapped so exceptions are logged and swallowed. | Spec 006 D3/D20: the tracer is sync, never raises, never blocks on network. API names were checked against `langfuse==5.1.0` source (`Langfuse.start_observation`, `create_event`, `create_trace_id(seed=…)`, `propagate_attributes`, `flush`, `shutdown`, the `span_exporter` constructor parameter, `LangfuseOtelSpanAttributes`). |
| D15 | **Langfuse trace id:** if the caller's `trace_id` is 32 lowercase hex characters, it is used as-is; otherwise `Langfuse.create_trace_id(seed=trace_id)`. Session grouping uses `propagate_attributes(session_id=…, trace_name="chat_turn")` around every observation. | Langfuse 5 requires W3C trace ids. Spec 008 and the chat CLI pass `uuid4().hex`, so the id printed or logged is the one shown in Langfuse. Handoff 7: random session id, no IP addresses. |
| D16 | **Intent on every observation.** The tracer remembers `trace_id → intent` from the router node's attributes (bounded at 1,024 traces, oldest evicted). Every later observation of that trace gets metadata `intent` and tag `intent:<value>`. | Draft: "on every graph node — model, tokens, cost, latency, intent". The router node is always the first node, so all later nodes carry it. The router's own generation is recorded before routing completes, so only the router span carries intent for that step. |
| D17 | **Span timing.** Observations are created after the fact (the port receives `latency_ms`, not a start time, and the 5.x `start_observation` has no `start_time` parameter). The adapter takes `t0 = time.time_ns()`, starts the observation, then ends it at `end_time = t0 + latency_ns`. `latency_ms` is also stored in metadata. | Durations in Langfuse match the measured latency. Timestamps are shifted by at most one node's latency, which is acceptable for a per-turn trace view. |
| D18 | **Tracing is optional locally.** If both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are empty, a `NullTracer` is used and a warning is logged once at startup. Exactly one set is a `ConfigError`. `LANGFUSE_BASE_URL` defaults to `https://cloud.langfuse.com`. | A developer can smoke-test with only an OpenRouter key. A half-configured pair is a mistake worth failing on. Handoff 8: Langfuse cloud free tier. |
| D19 | **Composition root at `backend/composition.py`** (outside `graph/` and `adapters/`, the only module that imports both). `Settings.from_env(environ)` reads env and `build_runtime(settings, …)` returns a `Runtime(assistant, close_callback)`, closed with `await runtime.aclose()`. Env is read only here, never inside adapters. No `.env` loader dependency: local runs use `uv run --env-file .env …`. | Handoff 4.1 hexagonal layering; spec 006 deferred the composition root to this spec. `uv` already supports `--env-file`, so `python-dotenv` would be an unjustified dependency. |
| D20 | **Milestone 6 is verified locally by a CLI, `python -m backend.chat "<message>" [--roll] [--modifier N]`**. It prints the reply, citations, move card and ids, then flushes traces before exit. | The FastAPI app is spec 008. A CLI is the smallest way to make "end-to-end chat works locally" checkable now. |
| D21 | **Automated tests never need real keys.** OpenRouter is exercised through the real `openai` SDK with an injected `httpx2.AsyncClient(transport=httpx2.MockTransport(…))`; `httpx2` is the HTTP library `openai` 3.x depends on. This checks request serialisation and response parsing. Langfuse is exercised through the real SDK with an injected OpenTelemetry `InMemorySpanExporter`, checking the exported span attributes. The retriever and index build use a deterministic `FakeEmbedder`. Two end-to-end tests run `build_runtime` with all three seams: a rules turn that produces a cited answer and exported spans with model, tokens and cost, and a move turn with a roll. No socket is opened (spec 006 D24 guard). Real-key verification is a documented owner step (see *Success Criteria*). | Handoff 6.4 (no paid API calls in CI). Testing at the HTTP and exporter boundary gives confidence that the wiring matches the real wire format, not just our own fakes. |
| D22 | **Port errors.** Every provider failure becomes `PortError` with a message naming the operation, the exception class and, for HTTP status errors, the status code. Never the API key, headers or response body. Spec 006 traces `str(exc)`. | Spec 006 D19 and its security note: "spec 007 adapters must not put secrets in them". |
| D23 | **Startup failures are loud.** Missing or invalid env → `ConfigError` listing every problem. Missing or corrupt index or normalized files → `ValueError`/`FileNotFoundError` naming the file. Embedding-model mismatch → `ConfigError`. No lazy loading. | Fail-fast at boot beats a first-request failure on Cloud Run. Same style as spec 005 D11 (`ValueError`). |
| D24 | **The JSON rulebook repository loads only `moves.json`**, via spec 005's `move_from_dict`, keeps file order, and rejects duplicate ids. Sections are not loaded at runtime: the retriever reads its own `chunks.json`. | The `RulebookRepository` port only has `list_moves`/`get_move` (spec 006). Loading 300+ sections nobody reads would waste memory. |
| D25 | **ADR numbers:** next free numbers in `docs/decisions.md` at implementation time (ADR-012, -013, -014 if specs 002–006 landed first). | Spec 005 D16 / 006 D26 precedent. |
| D26 | **`GraphSettings` stay at spec 006 defaults**, constructed with no arguments. No env overrides. | Not requested. Tuning belongs to spec 010 (spec 006 D25). |

**Open risks.**
- (a) **OpenRouter `usage.cost`.** If a provider omits `usage.cost`, `cost_usd` is `None` and Langfuse shows no cost for that generation, so milestone 6 fails for that model. The owner smoke check (*Success Criteria*) verifies it. The fallback is a Langfuse custom model price (UI setting), with no code change.
- (b) **Langfuse 5.x behaviour.** API names were checked against the 5.1.0 source. Two behaviours are asserted by tests rather than assumed: `propagate_attributes` applying `session.id`/tags to spans started with `trace_context`, and the JSON serialisation of usage/cost attributes. Langfuse keeps one resource manager per public key, so tests use a unique public key per client. If a minor upgrade changes attribute serialisation, only `test_adapters_langfuse.py` breaks.
- (c) **Structured-output support varies by model.** With `require_parameters`, an unsupported model yields an OpenRouter error, which becomes `PortError` and then spec 006's error reply. The owner smoke check covers the chosen models.
- (d) **Chunk size constants are unmeasured** against the real data (`MAX_CHUNK_CHARS`, `EMBED_MAX_CHARS`). The build CLI prints chunk statistics so story 2 can check them. They are tunable in spec 010.
- (e) **Binary file in git.** `data/index/embeddings.npy` (~2–3 MB) is committed and replaced wholesale on each rebuild. That is acceptable at this size (D4).
- (f) **Committed index may be absent.** The implementer may lack an OpenRouter key, so the index might not be committed by the story that builds the CLI. The freshness test then skips with an explicit reason and `build_runtime` fails at startup. Committing the index is an owner step in *Success Criteria*.
- (g) Spec 006 open risk (b) still applies: `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` must stay unset. They are not added to `.env.example`.

## Architecture / Design Overview

```
OFFLINE (owner, needs OPENROUTER_API_KEY)                     RUNTIME (python -m backend.chat, later spec 008)
data/normalized/{sections,moves}.json                         env ──▶ Settings.from_env ──▶ build_runtime
   │ chunking.build_chunks (pure)                                          │
   ▼                                                                       ├─ OpenRouterLLMClient(AsyncOpenAI) ── LLMClient
IndexChunk[] ──index_text──▶ OpenRouterEmbedder ──▶ vectors                ├─ HybridRetriever(load_index(data/index),
   │                                                  │                    │      OpenRouterEmbedder) ────────── Retriever
   └──────────── write_index ◀────────────────────────┘                    │      ├ vector: E·q  (NumPy)
                     ▼                                                     │      ├ BM25 (built at load)
            data/index/{manifest.json, chunks.json, embeddings.npy}        │      └ RRF → dedup section_id → top k
                     │ committed; spec 011 COPYs into image                ├─ LangfuseTracer | NullTracer ─────── Tracer
                     └────────────────────────────────────────────────────▶├─ JsonRulebookRepository(moves.json) ─ RulebookRepository
                                                                           └─ build_assistant(GraphDeps(...))  (spec 006)
```

Layering: `backend/adapters/**` imports `backend.ports.*`, `backend.domain.*`, other adapters, the stdlib and the three new libraries. It never imports `backend.graph` or `backend.api`. Only `backend/composition.py` and `backend/chat.py` import adapters and graph together. Spec 006's layering tests (ports and graph never import adapters) stay green.

## Configuration

**Environment variables.** Read only by `backend/composition.py`. Empty or whitespace-only counts as unset.

| Variable | Required | Meaning |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | yes (runtime and index build) | Bearer key for chat and embeddings (D1). |
| `MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER` | yes (runtime) | OpenRouter model ids per `ModelRole` (D13). |
| `MODEL_EMBEDDINGS` | yes (runtime and index build) | OpenRouter embedding model id; must equal the index manifest's `embedding_model` at runtime (D2). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | both or neither | Langfuse project keys; neither → `NullTracer` (D18). |
| `LANGFUSE_BASE_URL` | no | Default `https://cloud.langfuse.com`. |

**`.env.example`** (modify, additive). The existing header and all four `MODEL_*` lines are kept unchanged, so no key is duplicated. One comment line is inserted directly above the existing `MODEL_EMBEDDINGS=` line:

```dotenv
# Must equal "embedding_model" in data/index/manifest.json (rebuild the index after changing it).
```

These lines are appended at the end of the file:

```dotenv
# OpenRouter (spec 007): one key for chat models and embeddings.
OPENROUTER_API_KEY=

# Langfuse tracing (spec 007). Leave both keys empty to disable tracing locally.
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
# Optional; defaults to https://cloud.langfuse.com
LANGFUSE_BASE_URL=
```

**Constants** (not env-configurable): `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"`, `CHAT_TIMEOUT_S = 30.0`, `EMBEDDINGS_TIMEOUT_S = 15.0`, `MAX_RETRIES = 1`, `EMBED_BATCH_SIZE = 64` (`openrouter.py`). `MAX_CHUNK_CHARS = 6000`, `EMBED_MAX_CHARS = 24000`, `EXCLUDED_CHAPTERS = frozenset({"thanks"})` (`chunking.py`). `CANDIDATES = 30`, `RRF_K = 60` (`hybrid.py`). `BM25_K1 = 1.2`, `BM25_B = 0.75` (`bm25.py`). `DEFAULT_INDEX_DIR = REPO_ROOT / "data/index"` and `DEFAULT_NORMALIZED_DIR = REPO_ROOT / "data/normalized"`, where `REPO_ROOT = Path(__file__).resolve().parents[1]` (`composition.py`).

**`pyproject.toml`** (additive): `uv add openai langfuse numpy` appends three entries `"<name>>=<resolved version>"` to `[project].dependencies` (after spec 006's `langgraph`) and updates `uv.lock`. No tool-config change.

## Data Model

No database. New in-memory types are `@dataclass(frozen=True, slots=True)` validated in `__post_init__` with `ValueError` (spec 005 D11). The rules are in *Validation Rules*.

```python
# backend/ports/llm.py   (modified, additive — D11)
class LLMResponse: text: str; model: str; input_tokens: int; output_tokens: int
                   cost_usd: float | None = None        # new; provider-reported USD cost

# backend/adapters/retrieval/chunking.py
class IndexChunk:  chunk_id: str        # section_id if parts == 1, else f"{section_id}#{part}"
                   section_id: str; title: str; chapter: str; anchor_url: str
                   type: ChunkType      # spec 006 Literal["section", "move"]
                   part: int; parts: int                 # 1-based; 1/1 when not split
                   text: str                             # raw Markdown part (non-empty)
                   index_text: str                       # D10 header + text (not truncated)
def build_chunks(sections: Sequence[Section], moves: Sequence[Move]) -> tuple[IndexChunk, ...]: ...
def chunks_to_json(chunks: Sequence[IndexChunk]) -> str: ...    # deterministic serialisation

# backend/adapters/retrieval/embedder.py
class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...   # same order/length; raises PortError

# backend/adapters/retrieval/bm25.py
def tokenize(text: str) -> list[str]: ...
class BM25Index:
    def __init__(self, documents: Sequence[str]) -> None: ...
    def scores(self, query: str) -> list[float]: ...      # one per document, >= 0

# backend/adapters/retrieval/index.py
FORMAT_VERSION: Final = 1
class IndexManifest: format_version: int; embedding_model: str; dimensions: int
                     chunk_count: int; chunks_sha256: str
class LoadedIndex:   manifest: IndexManifest; chunks: tuple[IndexChunk, ...]
                     embeddings: NDArray[np.float32]      # shape (chunk_count, dimensions)
def write_index(out_dir: Path, chunks: Sequence[IndexChunk], vectors: Sequence[Sequence[float]],
                embedding_model: str) -> IndexManifest: ...
def load_index(index_dir: Path) -> LoadedIndex: ...

# backend/adapters/retrieval/hybrid.py
class HybridRetriever:                                   # satisfies ports.retriever.Retriever
    def __init__(self, index: LoadedIndex, embedder: Embedder) -> None: ...   # builds BM25
    async def retrieve(self, query: str, k: int) -> Sequence[RetrievedChunk]: ...

# backend/adapters/openrouter.py
def make_openrouter_client(api_key: str, *, timeout: float,
                           http_client: httpx2.AsyncClient | None = None) -> AsyncOpenAI: ...
class OpenRouterLLMClient:                               # satisfies ports.llm.LLMClient
    def __init__(self, client: AsyncOpenAI, models: Mapping[ModelRole, str]) -> None: ...
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
class OpenRouterEmbedder:                                # satisfies Embedder
    def __init__(self, client: AsyncOpenAI, model: str, batch_size: int = EMBED_BATCH_SIZE) -> None: ...
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

# backend/adapters/langfuse_tracer.py
class LangfuseTracer:                                    # satisfies ports.tracer.Tracer
    def __init__(self, client: Langfuse) -> None: ...
    def record_node(self, trace: NodeTrace) -> None: ...
    def record_generation(self, trace: GenerationTrace) -> None: ...
    def record_event(self, event: TraceEvent) -> None: ...
    def flush(self) -> None: ...                         # never raises
    def close(self) -> None: ...                         # client.shutdown(); never raises
def make_langfuse_tracer(public_key: str, secret_key: str, base_url: str, *,
                         span_exporter: SpanExporter | None = None) -> LangfuseTracer: ...

# backend/adapters/null_tracer.py
class NullTracer:  # record_* do nothing; flush()/close() do nothing

# backend/adapters/json_rulebook.py
class JsonRulebookRepository:                            # satisfies ports.rulebook.RulebookRepository
    def __init__(self, moves: Sequence[Move]) -> None: ...   # ValueError on duplicate id
    @classmethod
    def from_dir(cls, normalized_dir: Path) -> JsonRulebookRepository: ...   # reads moves.json
    def list_moves(self) -> Sequence[Move]: ...
    def get_move(self, move_id: str) -> Move | None: ...

# backend/adapters/retrieval/build.py
def make_embedder(api_key: str, model: str) -> Embedder: ...   # OpenRouterEmbedder; tests monkeypatch it
def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int: ...

# backend/composition.py
class ConfigError(Exception): ...
ENV_VARS: Final[tuple[str, ...]]    # the eight names in Configuration, in table order
class LangfuseSettings: public_key: str = field(repr=False); secret_key: str = field(repr=False); base_url: str
class Settings: openrouter_api_key: str = field(repr=False)
                model_router: str; model_classifier: str; model_answer: str; model_embeddings: str
                langfuse: LangfuseSettings | None
    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings: ...        # ConfigError listing all problems
class Runtime:  assistant: Assistant
                close_callback: Callable[[], Awaitable[None]]   # build_runtime supplies it; tests may pass any coroutine fn
    async def aclose(self) -> None: ...      # awaits close_callback once (idempotent)
def build_runtime(settings: Settings, *, index_dir: Path = DEFAULT_INDEX_DIR,
                  normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
                  http_client: httpx2.AsyncClient | None = None,     # test seam (D21)
                  span_exporter: SpanExporter | None = None,         # test seam (D21)
                  rng: RandomSource | None = None) -> Runtime: ...   # default random.Random()

# backend/chat.py
def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int: ...
```

**Index artifact** (`data/index/`, committed; written by `write_index`. All JSON is UTF-8, `ensure_ascii=False`, `indent=2`, LF, trailing newline, per spec 002 D14):

| File | Content |
|------|---------|
| `manifest.json` | Object `{"format_version": 1, "embedding_model": str, "dimensions": int, "chunk_count": int, "chunks_sha256": str}` (keys in this order). `chunks_sha256` is the hex SHA-256 of the exact `chunks.json` bytes. |
| `chunks.json` | `chunks_to_json(chunks)`: an array of objects with keys in order `chunk_id, section_id, title, chapter, anchor_url, type, part, parts, text, index_text`, in `build_chunks` order. |
| `embeddings.npy` | `np.save(..., allow_pickle=False)` of a float32 C-contiguous array of shape `(chunk_count, dimensions)`, with row *i* = L2-normalised embedding of chunk *i*'s `index_text[:EMBED_MAX_CHARS]`. |

**Chunk order and ids.** Chunks follow `sections.json` `order`. A move chunk takes the position of the section it replaces. Parts of a split section are consecutive. `chunk_id` values are unique.

## Impact on Existing Code

| Path | Action | Notes |
|------|--------|-------|
| `backend/ports/llm.py` (new in 006) | modify — **additive** | Add trailing field `cost_usd: float \| None = None` to `LLMResponse` and its validation. Positional and keyword constructions with four arguments are unchanged, `FakeLLMClient` is unchanged, and every spec 006 test passes unmodified. `LLMClient.generate` is unchanged. |
| `backend/tests/test_ports.py` (new in 006) | modify — **additive** | Add `test_llm_response_cost_validation` (*Testing*). Existing tests untouched. |
| `pyproject.toml` (new in 001) | modify — **additive** | Three dependencies (see *Configuration*). Existing commands are unchanged. |
| `uv.lock` (new in 001) | modify — **additive** | Regenerated by `uv add`. |
| `.env.example` (new in 001) | modify — **additive** | Lines in *Configuration*. Every line still matches spec 001's `KEY=` pattern, and keys stay unique, so `test_env_example_declares_keys_without_values` keeps passing. |
| `docs/decisions.md` (new in 001) | modify — **additive** | Three ADRs (*Documentation*). |
| `docs/architecture.md` (new in 001, rewritten by 006) | modify — **additive** | Append the section "Adapters and composition root" (*Documentation*). Spec 006 content is kept. |
| `README.md` (new in 001, extended by 004) | modify — **additive** | Add the subsection "Running the assistant locally" at the end of `## Development` (*Documentation*). The `## Attribution` section is untouched, so spec 001's README test is unaffected. |
| `backend/adapters/__init__.py` (new in 001) | unchanged | Stays empty. |
| `backend/adapters/openrouter.py` (new) | create | Client factory, `OpenRouterLLMClient`, `OpenRouterEmbedder`. |
| `backend/adapters/langfuse_tracer.py` (new) | create | `LangfuseTracer`, `make_langfuse_tracer`. |
| `backend/adapters/null_tracer.py` (new) | create | `NullTracer`. |
| `backend/adapters/json_rulebook.py` (new) | create | `JsonRulebookRepository`. |
| `backend/adapters/retrieval/__init__.py` (new) | create | Empty. |
| `backend/adapters/retrieval/chunking.py` (new) | create | `IndexChunk`, `build_chunks`, `chunks_to_json`, constants. |
| `backend/adapters/retrieval/embedder.py` (new) | create | `Embedder` protocol. |
| `backend/adapters/retrieval/bm25.py` (new) | create | `tokenize`, `BM25Index`. |
| `backend/adapters/retrieval/index.py` (new) | create | Manifest, `write_index`, `load_index`. |
| `backend/adapters/retrieval/hybrid.py` (new) | create | `HybridRetriever`. |
| `backend/adapters/retrieval/build.py` (new) | create | Index build CLI (`main(argv, environ) -> int`, `if __name__ == "__main__"`). |
| `backend/composition.py` (new) | create | Settings, `build_runtime`, `Runtime`. |
| `backend/chat.py` (new) | create | Local chat CLI. |
| `data/index/manifest.json`, `data/index/chunks.json`, `data/index/embeddings.npy` (new) | create | Generated by the build CLI with a real key and committed (owner step, open risk f). |
| `backend/tests/fakes/embedder.py` (new) | create | `FakeEmbedder` (*Testing*). |
| `backend/tests/adapter_helpers.py` (new) | create | Mock-transport and exporter helpers (*Testing*). Not collected by pytest. |
| `backend/tests/test_adapters_openrouter.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_chunking.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_bm25.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_index.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_hybrid.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_langfuse.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_rulebook.py` (new) | create | *Testing*. |
| `backend/tests/test_composition.py` (new) | create | *Testing*. |
| `backend/tests/test_adapters_layering.py` (new) | create | *Testing*. |
| `backend/domain/urls.py` (new in 006) | unchanged | `section_url` is used for `anchor_url` (D9). |
| `backend/tests/conftest.py` (new in 006) | unchanged | The no-network guard stays active for every new test. |
| `backend/tests/fakes/llm.py`, `retriever.py`, `tracer.py`, `rulebook.py` (new in 006) | unchanged | Used by `test_chat_cli_*`. |
| `backend/tests/domain_helpers.py` (new in 005) | unchanged | Its fixture move dicts and `ScriptedRandom` are reused. |

No change to any `backend/graph/` or `backend/domain/` module, to the spec 006 fakes or test guard listed above, to CI, `ingestion/` or `site/`. CI stays secret-free: the new tests are offline.

## Adapter Behaviour

### OpenRouter (`openrouter.py`)

`make_openrouter_client` returns `AsyncOpenAI(api_key=…, base_url=OPENROUTER_BASE_URL, timeout=…, max_retries=MAX_RETRIES, http_client=…)`. The composition root creates one chat client (`CHAT_TIMEOUT_S`) and one embeddings client (`EMBEDDINGS_TIMEOUT_S`) with the same key and the same optional `http_client`.

`OpenRouterLLMClient.generate(request)` sends `chat.completions.create` with this body (JSON on the wire):

```json
{"model": "<models[request.role]>",
 "messages": [{"role": "system", "content": "<request.system>"}, {"role": "user", "content": "<request.user>"}],
 "max_tokens": 100, "temperature": 0.0,
 "usage": {"include": true},
 "response_format": {"type": "json_schema",
                     "json_schema": {"name": "<schema_name>", "strict": true, "schema": {"...": "response_schema"}}},
 "provider": {"require_parameters": true}}
```

`response_format` and `provider` are sent only when `request.response_schema` is set. `usage` and `provider` go through `extra_body`.

Response mapping:

| `LLMResponse` field | Source |
|---------------------|--------|
| `text` | `choices[0].message.content`, or `""` if `None`. |
| `model` | `response.model` if non-empty, else the requested model id. |
| `input_tokens`, `output_tokens` | `usage.prompt_tokens`, `usage.completion_tokens`; `0` if `usage` is absent. |
| `cost_usd` | `usage` extra field `cost` (pydantic `model_extra`) if it is an `int`/`float` (not `bool`), finite and ≥ 0, as `float`; otherwise `None`. |

Failures raise `PortError` (D22):

| Condition | `PortError` message |
|-----------|---------------------|
| `openai.APIStatusError` (after SDK retries) | `openrouter chat request failed: <ClassName> (status <code>)` |
| other `openai.APIError` (connection, timeout) | `openrouter chat request failed: <ClassName>` |
| empty `choices`, or `choices[0].finish_reason == "error"` | `openrouter chat response had no usable choice` |

The constructor raises `ValueError` if `models` lacks any of `router`, `classifier`, `answer`, or has an empty value.

`OpenRouterEmbedder.embed(texts)`:
- Empty input returns `[]` with no request.
- Otherwise it calls `embeddings.create(model=…, input=batch, encoding_format="float")` per batch of `batch_size`, in order.
- Within a batch, vectors are ordered by `data[i].index`.
- `PortError` cases:
  - SDK errors: `openrouter embeddings request failed: …` (same format as chat).
  - Count mismatch: `openrouter embeddings response has <n> vectors for <m> inputs`.
  - Inconsistent or zero dimensions: `openrouter embeddings response has inconsistent dimensions`.

### Chunking (`retrieval/chunking.py`)

`build_chunks(sections, moves)` runs these steps in order:

1. Build `move_by_section = {m.section_id: m for m in moves}` and `chapter_title = {s.chapter: s.title for s in sections if s.id == s.chapter}`.
2. For each section in `order`:
   - Skip it if `section.chapter in EXCLUDED_CHAPTERS`.
   - If the section's id is in `move_by_section`, emit one move chunk: `title = move.name`, `text = move.body_markdown.strip()`, `type = "move"`, `part = parts = 1`.
   - Else, if `text_markdown.strip()` is empty, skip it.
   - Else, if the stripped text has length ≤ `MAX_CHUNK_CHARS`, emit one section chunk.
   - Else, split it: the blocks are the text split on `\n\s*\n`, stripped, non-empty. Pack greedily: add a block to the current part while `len(current) + 2 + len(block) ≤ MAX_CHUNK_CHARS`, otherwise close the part and start a new one. A single block longer than the limit is a part on its own. Parts are joined with `"\n\n"`.
3. Every chunk gets `chapter = section.chapter`, `anchor_url = section_url(section.id)` and `index_text` per D10.
4. Raise `ValueError` if a move's `section_id` has no matching section (spec 002 guarantees it exists).

`chunks_to_json` serialises per *Data Model*. It is the single serialiser used by both `write_index` and the freshness test.

### BM25 (`retrieval/bm25.py`)

`tokenize(text)` follows D6. `BM25Index(documents)` stores each document's term frequencies, its length in tokens, the average length `avgdl`, `df` per term, and `N`. `scores(query)` takes the unique query tokens `q`. For each document `d`, the score is:

`Σ_{t∈q, tf>0} idf(t) · tf·(k1+1) / (tf + k1·(1 − b + b·|d|/avgdl))`, with `idf(t) = ln(1 + (N − df + 0.5)/(df + 0.5))`.

If `avgdl == 0`, every score is 0.0. A query with no tokens gives all zeros.

### Index (`retrieval/index.py`) and build CLI (`retrieval/build.py`)

`write_index` validates that `len(vectors) == len(chunks) > 0`, that all vectors have the same non-zero dimension, and that each vector is finite with norm > 0. It L2-normalises each row and writes the three files. It returns the manifest.

`load_index` checks, in this order, and raises `ValueError` naming the file and the problem on the first failure:
1. All three files exist (`FileNotFoundError` otherwise).
2. The manifest has exactly the five keys with the right types, and `format_version == 1`.
3. The SHA-256 of `chunks.json` bytes equals `chunks_sha256`.
4. Each chunk object has exactly the ten keys and builds a valid `IndexChunk`.
5. `len(chunks) == chunk_count`.
6. `np.load(allow_pickle=False)` gives dtype float32 with shape `(chunk_count, dimensions)`.
7. All values are finite and every row norm is within `1 ± 1e-3`.

The build CLI is `uv run --env-file .env python -m backend.adapters.retrieval.build [--normalized DIR] [--out DIR]`, with defaults `data/normalized` and `data/index`.
- It reads `OPENROUTER_API_KEY` and `MODEL_EMBEDDINGS` from `environ`; a missing key is reported as a `ConfigError`-style message.
- It loads the sections and moves with spec 005's parsers and calls `build_chunks`.
- It embeds `index_text[:EMBED_MAX_CHARS]` for every chunk. For each truncated chunk it prints `index-build: warning: truncated <chunk_id> (<n> chars)` to stderr.
- It calls `write_index` only after every batch has succeeded, so a failure writes nothing.
- On success it prints `index-build: <chunk_count> chunks (<move> moves, <split> split sections, max <c> chars), <dimensions> dims, model <model>` and exits `0`.
- Any error exits `2` with `index-build: error: <message>` on stderr.

### Hybrid retriever (`retrieval/hybrid.py`)

`HybridRetriever.__init__` builds `BM25Index([c.index_text for c in index.chunks])`. `retrieve(query, k)` works as follows:
- `k < 1` raises `ValueError`. A `query` that is empty after `strip()` returns `[]` with no embedding call.
- Embed `[query]`. An `Embedder` error propagates as `PortError`. A zero-norm query vector raises `PortError("query embedding is a zero vector")`.
- Vector ranking: cosine scores = `embeddings @ (q/‖q‖)`, then the top `CANDIDATES` by score descending, ties broken by chunk index.
- BM25 ranking: chunks with score > 0, top `CANDIDATES`, same tie rule.
- Fuse with RRF (D7), sort by fused score descending then chunk index, keep the first chunk per `section_id`, and cut to `k`.
- Map each chunk to `RetrievedChunk(section_id, title, chapter, anchor_url, type, text, score)`.

### Langfuse tracer (`langfuse_tracer.py`)

`make_langfuse_tracer` constructs `Langfuse(public_key=…, secret_key=…, base_url=…, span_exporter=span_exporter)`.

Every `record_*` call runs inside `try/except Exception`. On failure it logs at WARNING on logger `backend.adapters.langfuse` the message `langfuse <method> failed: <ClassName>`, never the payload, and returns `None`.

Each call:
1. Resolves the Langfuse trace id (D15).
2. Opens `propagate_attributes(session_id=<session_id>, trace_name="chat_turn", metadata={"intent": i}, tags=[f"intent:{i}"])`, omitting metadata and tags while the intent is unknown (D16).
3. Inside that context, creates the observation with `trace_context={"trace_id": <id>}` and ends it per D17.

| Port call | Langfuse observation |
|-----------|----------------------|
| `record_node(t)` | `start_observation(as_type="span", name=t.node, metadata={**t.attributes, "latency_ms": t.latency_ms}, level="ERROR" if t.attributes.get("error") is True else None)`. If `t.node == "router"` and `t.attributes["intent"]` is a `str`, the intent is stored first (D16), so the router span carries it too. |
| `record_generation(t)` | `start_observation(as_type="generation", name=t.node, model=t.response.model, model_parameters={"max_tokens": r.max_tokens, "temperature": r.temperature}, input=[{"role": "system", "content": r.system}, {"role": "user", "content": r.user}], output=t.response.text, usage_details={"input": t.response.input_tokens, "output": t.response.output_tokens}, cost_details={"total": t.response.cost_usd} if not None else None, metadata={"role": r.role, "schema_name": r.schema_name, "latency_ms": t.latency_ms})`, where `r = t.request`. |
| `record_event(e)` | `create_event(name=e.name, metadata=dict(e.attributes), level=<see below>)`. No `end` call. |

Event levels:

| Level | Event names |
|-------|-------------|
| `ERROR` | `port_error`, `llm_output_invalid` |
| `WARNING` | `citations_stripped`, `no_valid_citation`, `classifier_unknown_move`, `classifier_alternatives_stripped`, `classifier_stat_overridden` |
| `DEFAULT` | everything else, including `clarification_requested` |

`flush()` calls `client.flush()` and `close()` calls `client.shutdown()`, both guarded. Neither is part of the `Tracer` port; `Runtime.aclose` and the chat CLI call them.

### Rulebook repository (`json_rulebook.py`)

`from_dir` reads `<dir>/moves.json` (UTF-8). The top level must be a JSON array, otherwise `ValueError`. Each element goes through `move_from_dict`, and errors are re-raised as `ValueError` prefixed with the file path. `get_move` uses a dict built at construction, and `list_moves` returns a tuple in file order.

## Composition Root and Chat CLI

`Settings.from_env(environ)` collects every problem before raising a single `ConfigError`. The message is `invalid configuration: ` followed by the problems joined with `; `, each one of:
- `<VAR> is required`
- `LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must both be set or both be empty`
- `LANGFUSE_BASE_URL must start with https:// or http://`

Values are stripped. Secrets never appear in `repr(settings)` or in any message.

`build_runtime(settings, …)`:
1. `index = load_index(index_dir)`. If `index.manifest.embedding_model != settings.model_embeddings`, raise `ConfigError("index was built with '<a>' but MODEL_EMBEDDINGS is '<b>'; rebuild the index (python -m backend.adapters.retrieval.build)")`.
2. `rulebook = JsonRulebookRepository.from_dir(normalized_dir)`.
3. Create the chat and embeddings clients (*Adapter Behaviour*), the `OpenRouterLLMClient` with `{"router": model_router, "classifier": model_classifier, "answer": model_answer}`, and `HybridRetriever(index, OpenRouterEmbedder(embeddings_client, model_embeddings))`.
4. Tracer: if `settings.langfuse` is set, use `make_langfuse_tracer(..., span_exporter=span_exporter)`. Otherwise use `NullTracer()` and log WARNING `Langfuse keys not set; tracing disabled` on logger `backend.composition`.
5. `assistant = build_assistant(GraphDeps(llm, retriever, tracer, rulebook, rng or random.Random()))` (spec 006; default `GraphSettings()`, D26).
6. Return `Runtime(assistant, close_callback)`, where `close_callback` awaits `close()` on both `AsyncOpenAI` clients and then calls `tracer.close()`. `Runtime.aclose()` runs it at most once.

`backend/chat.py` `main(argv, environ)` (`environ` defaults to `os.environ`; `if __name__ == "__main__": raise SystemExit(main())`):
- Arguments: positional `message`, `--roll` (flag), `--modifier INT`.
- `Settings.from_env` then `build_runtime`. On `ConfigError`, `ValueError` or `FileNotFoundError`, print `chat: error: <message>` to stderr and return `2`.
- Build `TurnInput(message, session_id=uuid4().hex, trace_id=uuid4().hex, roll_requested=args.roll, modifier=args.modifier)`. A `ValueError` from `TurnInput` returns `2` with the same message format.
- `asyncio.run` one function that runs the turn and then `await runtime.aclose()` in `finally`. `aclose` flushes traces.
- Print to stdout, in order:
  1. `reply.text`.
  2. If there are citations: a blank line, `Citations:`, then `- <title>: <url>` per citation.
  3. If there is a move card: a blank line, `Move: <name> (<url>)`, then one line per band: `10+: <strong_hit>`, `7-9: <weak_hit>`, `6-: <miss or "Not stated by this move.">`. These lines are omitted when `outcomes is None`.
  4. A blank line, then `kind=<kind> intent=<intent or "-"> trace_id=<trace_id> session_id=<session_id>`.
- Return `1` if `reply.kind == "error"`, else `0`.

## Validation Rules

All failures raise `ValueError` naming the type and field unless stated otherwise. "Non-empty" means non-empty after `strip()`.

| Subject | Field / input | Rule |
|---------|---------------|------|
| `LLMResponse` | `cost_usd` | `None`, or an `int`/`float` that is not `bool`, finite and ≥ 0. |
| `IndexChunk` | `chunk_id`, `section_id`, `title`, `chapter`, `text`, `index_text` | Non-empty; `section_id` matches spec 005 `SECTION_ID`; `chapter` matches `SLUG`. |
| `IndexChunk` | `anchor_url` | Equals `section_url(section_id)`. |
| `IndexChunk` | `type` | `"section"` or `"move"`; `"move"` implies `parts == 1`. |
| `IndexChunk` | `part`, `parts` | `int` (not `bool`), `1 ≤ part ≤ parts`; `chunk_id == section_id` iff `parts == 1`, else `f"{section_id}#{part}"`. |
| `IndexManifest` | all | `format_version == 1`; `embedding_model` non-empty; `dimensions ≥ 1`; `chunk_count ≥ 1`; `chunks_sha256` matches `^[0-9a-f]{64}$`. |
| Index files | consistency | See `load_index` checks. |
| `write_index` | vectors | Count equals chunk count; equal non-zero dimensions; finite; norm > 0. |
| `HybridRetriever.retrieve` | `k` | `int ≥ 1`. Empty query → `[]`. Result: `len ≤ k`, distinct `section_id`. |
| `OpenRouterLLMClient` | `models` | Keys `router`, `classifier`, `answer` all present, values non-empty. |
| `OpenRouterEmbedder` | `model`, `batch_size` | Non-empty; `batch_size ≥ 1`. |
| `JsonRulebookRepository` | moves | Valid per spec 005 `move_from_dict`; ids unique. |
| `Settings.from_env` | env | See *Configuration* and *Composition Root* (`ConfigError`). |
| `backend.chat` | `--modifier` | argparse `int`, then `TurnInput` range −10…10 (spec 006). |
| Embedding model | runtime | `MODEL_EMBEDDINGS` equals manifest `embedding_model` (`ConfigError`). |

## Authorization & Security

There are no endpoints or users in this spec; access control and abuse limits belong to spec 008.
- **Secrets:** they are read from env only in `composition.py` and the build CLI, and are `repr=False` on the settings types. They never appear in `PortError`, `ConfigError` or log messages (D22). `.env` stays git-ignored (spec 001). CI references no secrets.
- **Privacy (handoff 7):** traces carry only the caller-supplied `trace_id`/`session_id`. No IP address or request metadata reaches the adapters. Generation inputs (system prompt plus the user's message) and outputs are sent to Langfuse by design; this is stated in the tracing ADR.
- **Untrusted artifact loading:** `np.load(..., allow_pickle=False)` everywhere. JSON only otherwise.
- **Transport:** HTTPS endpoints (OpenRouter constant; Langfuse default). Every outbound call has a timeout and at most one retry (D12).
- **Cost bounding:** `max_tokens` from spec 006 is forwarded on every chat call (test-asserted). Embeddings are about 30 tokens per query. The spend cap is spec 008's.
- **No network in tests:** spec 006's socket guard stays active. Mock transports and in-memory exporters open no sockets.

## Testing

pytest with plain functions in flat files in `backend/tests/` (spec 005 D15). Async adapter calls run via `asyncio.run`. No test reads env vars from the process: settings are built from dict literals.

**Helpers.**
- `backend/tests/fakes/embedder.py`: `FakeEmbedder(dim=64, error: PortError | None = None)`. Each text becomes a hashed bag-of-words vector: for each `tokenize` token, `vec[int(sha256(token).hexdigest(), 16) % dim] += 1`. An all-zero result gets `vec[0] = 1`. It records each `texts` call in `calls` and raises `error` when set.
- `backend/tests/adapter_helpers.py`:
  - `mock_http(handler) -> httpx2.AsyncClient` with `MockTransport`.
  - `chat_completion_json(content, model="openai/test", prompt_tokens=12, completion_tokens=7, cost=0.00042)` returns an OpenRouter-shaped response dict, with `usage.cost` omitted when `cost=None`.
  - `embeddings_json(vectors, model)`.
  - `RecordingHandler`, which stores each `httpx2.Request` and its parsed JSON body and replies from a queue of `(status, json)`.
  - `memory_tracer() -> tuple[LangfuseTracer, InMemorySpanExporter]`, using `make_langfuse_tracer(f"pk-test-{uuid4().hex}", "sk-test", "https://langfuse.invalid", span_exporter=exporter)`.
  - `mini_normalized(tmp_path) -> Path`, which writes valid `sections.json`/`moves.json` (spec 002 shapes) to `tmp_path / "normalized"` and returns that directory. Contents, in this `order`:

    | # | Section id | chapter | title | `text_markdown` |
    |---|-----------|---------|-------|-----------------|
    | 0 | `moves` | `moves` | Moves | `"Moves are rules that tell you when they trigger."` |
    | 1–6 | `moves/<id>` for `hack-and-slash`, `defy-danger`, `volley`, `discern-realities`, `last-breath`, `make-camp` | `moves` | the move name | the move's `body_markdown` |
    | 7 | `moves/empty` | `moves` | Empty | `""` |
    | 8 | `gm` | `gm` | The GM | `"The GM's agenda and principles."` |
    | 9 | `gm/big-section` | `gm` | Big Section | 8 blocks `"Block {i}: " + "x" * 1500` (i = 1…8) joined by `"\n\n"`, so ≈ 12,100 chars and 3 parts |
    | 10 | `gm/huge-block` | `gm` | Huge Block | one block `"y" * 7000` |
    | 11 | `thanks` | `thanks` | Thanks | `"Backer One, Backer Two."` |

    `moves.json` = the six spec 005 fixture move dicts (`backend/tests/domain_helpers.py`), with `section_id` = `moves/<id>`. For `test_moves_never_split`, the test writes its own variant in which `hack-and-slash`'s `body_markdown` (and its section text) is `"z" * 7000`.
  - `VectorStubEmbedder(index_dir: Path, query_vectors: Mapping[str, Sequence[float]])`: for a text equal to a key of `query_vectors`, returns that vector; otherwise delegates to `FakeEmbedder()`. `test_bm25_rescues_exact_term` maps the query to the stored `embeddings.npy` row of the `volley` chunk.
  - `ScriptedEmbedder(vectors: Mapping[str, Sequence[float]])`: returns the mapped vector for each exact text and raises `AssertionError` for an unmapped text. `test_rrf_order` uses it for a hand-built two-chunk `LoadedIndex` (2-dim unit vectors, constructed in the test without `write_index`).

**`test_adapters_openrouter.py`**
- `test_chat_request_body_for_structured_call`: router request with schema. One POST to path `/api/v1/chat/completions`. Header `authorization == "Bearer test-key"`. The body has `model == "m-router"`, the two messages in order, `max_tokens == 100`, `temperature == 0.0`, `response_format.json_schema` with `name == "router_decision"`, `strict is True` and `schema` equal to the request schema, `provider == {"require_parameters": True}`, and `usage == {"include": True}`.
- `test_chat_request_body_without_schema`: answer role. `model == "m-answer"`, no `response_format`, no `provider`, `usage` present.
- `test_model_selected_per_role`: parametrized over the three roles, each mapping to its configured model.
- `test_response_mapping_with_cost`: the response maps to `LLMResponse(text, "openai/test", 12, 7, cost_usd=0.00042)`.
- `test_missing_cost_is_none`: `cost=None` in the response gives `cost_usd is None`.
- `test_null_content_becomes_empty_text`: `content: null` gives `text == ""`.
- `test_status_error_raises_port_error_without_secrets`: a 401 raises `PortError` whose message contains `AuthenticationError` and `401` and does not contain `test-key`.
- `test_server_error_retried_once_then_port_error`: two queued 500s give 2 requests, then `PortError`.
- `test_timeout_raises_port_error`: the handler raises `httpx2.ReadTimeout`, which gives `PortError` containing `APITimeoutError`.
- `test_no_choices_raises_port_error`: `choices: []` gives `PortError`.
- `test_missing_model_role_rejected`: `models` without `classifier` raises `ValueError`.
- `test_embedder_batches_in_order`: 130 texts with `batch_size=64` gives 3 requests with input sizes 64, 64, 2, `encoding_format == "float"`, and the configured model. Returned vectors follow input order even when a response lists `data` in reverse `index` order.
- `test_embedder_count_mismatch_raises`: 2 inputs and 1 vector raises `PortError`.
- `test_embedder_empty_input_no_request`: `embed([])` returns `[]` with zero requests.
- `test_adapters_satisfy_protocols`: annotated assignments `llm: LLMClient = OpenRouterLLMClient(...)`, `emb: Embedder = OpenRouterEmbedder(...)`.

**`test_adapters_chunking.py`** (uses `mini_normalized`, and the committed data where it exists)
- `test_move_section_replaced_by_move_chunk`: there is exactly one chunk with `section_id == "moves/hack-and-slash"`, with `type == "move"`, `title == "Hack and Slash"` and `text` equal to the move's `body_markdown` stripped.
- `test_thanks_chapter_excluded`: no chunk has `chapter == "thanks"`.
- `test_empty_sections_skipped`: a section with `text_markdown == ""` produces no chunk.
- `test_oversized_section_split_on_block_boundaries`: every part is ≤ 6000 characters unless it is a single block. Joining the parts with `"\n\n"` reproduces the normalised block sequence. Parts are consecutive with ids `<sid>#1…#n` and share `section_id`/`title`/`anchor_url`.
- `test_single_huge_block_kept_whole`: one 7,000-character paragraph becomes one part of 7,000 characters.
- `test_moves_never_split`: a move whose body is longer than 6,000 characters gives one chunk with `parts == 1`.
- `test_anchor_url_matches_url_contract`: for every chunk, `anchor_url == f"/rules/{section_id}/"` (spec 004 D1).
- `test_index_text_header`: a child section gives `"<chapter title> > <title>\n\n<text>"`; the root section gives `"<title>\n\n<text>"`.
- `test_build_chunks_deterministic`: two runs give equal `chunks_to_json` output.
- `test_committed_data_chunks_valid`: skipped with reason `data/normalized not built yet` if `data/normalized/sections.json` is absent. Otherwise it builds chunks from the committed data and checks: 21 move chunks, unique `chunk_id`s, no `thanks` chunk, and no section-type chunk whose id is a move's `section_id`.

**`test_adapters_bm25.py`**
- `test_tokenize`: `"Hack and Slash’s 10+ (STR)"` gives `["hack", "and", "slash", "s", "10", "str"]`.
- `test_exact_term_ranks_first`: three documents (Hack and Slash text, Defy Danger text, Volley text) and the query `"hack and slash"` put document 0 first with the highest score.
- `test_idf_never_negative`: a term in every document gives score ≥ 0.
- `test_no_overlap_scores_zero` and `test_empty_query_scores_zero`.
- `test_length_normalisation`: the same term frequency in a shorter document scores higher.

**`test_adapters_index.py`**
- `test_write_and_load_round_trip`: build from `mini_normalized` with `FakeEmbedder` into `tmp_path`, then load. The chunks are equal, the embeddings shape is `(n, 64)` float32 with unit rows, the manifest model matches, and the SHA-256 matches.
- `test_load_rejects_tampered_chunks`: editing one byte of `chunks.json` raises `ValueError` mentioning `chunks_sha256`.
- `test_load_rejects_shape_mismatch`: rewriting `embeddings.npy` with one row fewer raises `ValueError`.
- `test_load_rejects_non_finite` and `test_load_rejects_pickled_array` (an object-dtype array saved with pickle): both raise `ValueError`.
- `test_load_missing_file`: no `manifest.json` raises `FileNotFoundError`.
- `test_write_rejects_zero_vector`: raises `ValueError`.
- `test_build_cli_writes_index`: `build.main(["--normalized", d, "--out", o], environ={...})` with `build.make_embedder` monkeypatched to return `FakeEmbedder()` returns `0`, writes the three files, and prints the summary line.
- `test_build_cli_missing_key`: an `environ` without `OPENROUTER_API_KEY` returns `2` with stderr containing `OPENROUTER_API_KEY is required`, and writes nothing.
- `test_build_cli_provider_failure_writes_nothing`: `FakeEmbedder(error=PortError("down"))` returns `2`, and the output dir has no files.
- `test_committed_index_is_fresh`: skipped with reason `data/index not committed yet: run python -m backend.adapters.retrieval.build with OPENROUTER_API_KEY` when `data/index/manifest.json` is absent. Otherwise `chunks_to_json(build_chunks(committed data))` equals the committed `chunks.json` text, and `load_index("data/index")` succeeds.

**`test_adapters_hybrid.py`** (index built in `tmp_path` with `FakeEmbedder`)
- `test_returns_at_most_k_distinct_sections`: `k=3` gives ≤ 3 results with distinct `section_id`.
- `test_split_section_appears_once`: a query matching several parts of the oversized section returns that `section_id` once, with the best part's `text`.
- `test_bm25_rescues_exact_term`: `VectorStubEmbedder` returns, for the query, the stored vector of the `volley` chunk, so the vector ranking puts `volley` first. With the query `"last breath"`, `moves/last-breath` (BM25 #1, plus its vector rank) still ranks first, ahead of `volley` (vector #1 only, no BM25 hit).
- `test_rrf_order`: `ScriptedEmbedder` and a two-chunk corpus where chunk A (lower chunk index) is vector #1 and BM25 #2, and chunk B is vector #2 and BM25 #1. Both score exactly `1/61 + 1/62`, and A comes first by the chunk-index tie rule.
- `test_empty_query_no_embedding_call`: `"  "` gives `[]` and `FakeEmbedder.calls == []`.
- `test_embedder_error_is_port_error`: raises `PortError`.
- `test_k_must_be_positive`: `k=0` raises `ValueError`.
- `test_results_are_valid_retrieved_chunks`: `type` is in `{"section", "move"}`, `anchor_url` follows the contract, and scores are finite and non-increasing.
- `test_satisfies_retriever_protocol`: annotated assignment `r: Retriever = HybridRetriever(...)`.

**`test_adapters_langfuse.py`** (`memory_tracer()`, then `tracer.flush()`, then `exporter.get_finished_spans()`; attribute keys come from `langfuse.LangfuseOtelSpanAttributes`; JSON-valued attributes are decoded with `json.loads`)
- `test_node_span_exported`: `record_node(NodeTrace("ab" * 16, "s1", "retrieve", 12.5, {"count": 6}))` exports one span named `retrieve` whose trace id formatted `032x` equals the given id. `session.id` is `"s1"`, the trace name is `"chat_turn"`, the metadata contains `count` and `latency_ms`, and the duration is 12.5 ms within 1 ms.
- `test_non_hex_trace_id_mapped_deterministically`: `trace_id="t1"` gives the span trace id `Langfuse.create_trace_id(seed="t1")`.
- `test_generation_has_model_usage_and_cost`: a `GenerationTrace` with an `LLMResponse(..., model="openai/x", input_tokens=12, output_tokens=7, cost_usd=0.00042)` gives an observation of type `generation`, model `openai/x`, usage `{"input": 12, "output": 7}`, cost `{"total": 0.00042}`, and model parameters containing `max_tokens`.
- `test_generation_without_cost_has_no_cost_details`: `cost_usd=None` gives no cost attribute.
- `test_intent_propagates_after_router`: router node `{intent: "rules_question"}` followed by a retrieve node gives both spans tags containing `intent:rules_question`. A node recorded for another trace id has no intent tag.
- `test_event_levels`: `port_error` gives level `ERROR`, `citations_stripped` gives `WARNING`, and `clarification_requested` gives `DEFAULT`.
- `test_error_node_level`: attributes `{"error": True}` give level `ERROR`.
- `test_tracer_never_raises`: with `start_observation` and `create_event` monkeypatched on the client to raise `RuntimeError`, every `record_*` returns `None` and a WARNING containing `RuntimeError` is logged (`caplog`).
- `test_null_tracer_accepts_everything`: every method returns `None`.
- `test_tracers_satisfy_protocol`: annotated `Tracer` assignments for both tracers.

**`test_adapters_rulebook.py`**
- `test_loads_committed_moves`: skipped if `data/normalized/moves.json` is absent. Otherwise 21 moves load, with `list_moves()[0].id` equal to the first id in the file and `get_move("hack-and-slash").name == "Hack and Slash"`.
- `test_get_unknown_move_returns_none`.
- `test_duplicate_ids_rejected`: raises `ValueError`.
- `test_invalid_file_names_path`: a move with an extra key raises `ValueError` whose message contains the file path.
- `test_top_level_must_be_array`.

**`test_composition.py`**
- `test_settings_from_env_valid`: all values set give `Settings` with stripped values, and `langfuse.base_url` defaults to `https://cloud.langfuse.com`.
- `test_settings_lists_all_missing`: `{}` gives `ConfigError` naming `OPENROUTER_API_KEY`, `MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER` and `MODEL_EMBEDDINGS`.
- `test_whitespace_counts_as_unset`.
- `test_langfuse_half_configured_rejected`: only a public key gives `ConfigError`.
- `test_langfuse_absent_gives_null_tracer_and_warning`: both empty gives `langfuse is None`. `build_runtime` logs `tracing disabled` (`caplog`).
- `test_settings_repr_hides_secrets`: `repr(settings)` contains neither key value.
- `test_env_example_declares_every_setting`: every name in `ENV_VARS` appears as a key in `.env.example`.
- `test_embedding_model_mismatch_rejected`: an index built with `fake-embed` and `MODEL_EMBEDDINGS="other"` give `ConfigError` mentioning both names.
- `test_end_to_end_rules_turn_with_real_adapters` (the wiring proof, D21): index in `tmp_path` built with `FakeEmbedder`; `mini_normalized`; `http_client` = mock transport answering `/embeddings` from `FakeEmbedder` vectors and `/chat/completions` with a router JSON `{"intent": "rules_question", "confidence": 0.9}` followed by an answer citing `[[moves/hack-and-slash]]`; an in-memory span exporter. `build_runtime(...)`, then `runtime.assistant.run(TurnInput("How does hack and slash work?", session_id="s1", trace_id=<32-hex>))`, then `aclose()`. Assertions:
  - The reply kind is `rules_answer` with one citation whose url is `/rules/moves/hack-and-slash/`.
  - The two chat requests used `m-router`/`m-answer` with `max_tokens` 100/700.
  - The exported spans include nodes `router`, `retrieve`, `answer_with_citations` and `citation_validator`, and two generations with usage and cost.
  - Every span has `session.id == "s1"` and the given trace id.
- `test_end_to_end_move_turn_with_roll`: same setup with classifier JSON `hack-and-slash` 0.9, `roll_requested=True`, `modifier=1`, and an `rng` of spec 005's `ScriptedRandom([4, 5])`. The reply kind is `move`, the card outcome band is `strong_hit`, and the text ends with `Rolled 4 + 5 + 1 = 10: 10+.`.
- `test_chat_cli_config_error_exit_2`: `chat.main(["hi"], environ={})` returns `2` with stderr starting `chat: error: invalid configuration:`.
- `test_chat_cli_prints_reply_and_ids`: `build_runtime` is monkeypatched in `backend.chat` to return a runtime over spec 006 fakes with a scripted rules answer. The command returns `0`, and stdout contains the reply text, `Citations:`, `- Hack and Slash: /rules/moves/hack-and-slash/` and a final line matching `^kind=rules_answer intent=rules_question trace_id=[0-9a-f]{32} session_id=[0-9a-f]{32}$`.
- `test_chat_cli_error_reply_exit_1`: a fake LLM raising `PortError` gives return code `1`.

**`test_adapters_layering.py`** (AST scan, spec 005 D13 style)
- `test_adapters_do_not_import_graph_or_api`: no file under `backend/adapters/` imports `backend.graph` or `backend.api`. The test asserts that `openrouter.py` and `retrieval/hybrid.py` were scanned.
- `test_vendor_sdks_confined_to_adapters`: `openai`, `langfuse`, `numpy`, `httpx2` and `opentelemetry` are imported only under `backend/adapters/`, `backend/composition.py` and `backend/tests/`.

**`test_ports.py`** (additive)
- `test_llm_response_cost_validation`: `cost_usd=-0.01`, `nan` and `True` raise `ValueError`. `None`, `0.0` and `0.002` are accepted. A four-argument construction still works and has `cost_usd is None`.

**Manual / CI:** `uv sync --locked`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` (strict, zero errors), `uv run pytest`, all exit 0 with no env vars set.

## Documentation

- **ADR "Model provider: OpenRouter for chat and embeddings"**. Content from D1, D2, D11–D13 and D22. It must include:
  - The 2026-11-05 verification that OpenRouter serves embeddings.
  - The rejected alternatives (direct OpenAI key, local `fastembed`) and the override path.
  - The cost estimate.
  - The provisional starting model values, marked "to be replaced by spec 010's measured choice".
  - The `cost_usd` port addition.
- **ADR "Retrieval: section chunks, NumPy + in-house BM25 hybrid, committed index"**. Content from D3–D10. It must state the no-managed-vector-DB trade-off (handoff 4.3), why Chroma/LanceDB/FAISS and `rank-bm25`/`bm25s` were not chosen, the RRF parameters, the chunking rules and constants, and the rebuild command.
- **ADR "Tracing: Langfuse adapter"**. Content from D14–D18. It must state the trace-id rule, session and intent propagation, that IPs are never traced but prompts and messages are, the never-block mechanism, and spec 006 open risk (b).
- **`docs/architecture.md`**: append `## Adapters and composition root` with the diagram from *Architecture / Design Overview* and one line per adapter (port, library, key behaviour).
- **`README.md`**: under `## Development`, add `### Running the assistant locally`. Content: copy `.env.example` to `.env` and fill `OPENROUTER_API_KEY`, the four `MODEL_*` values and optionally the Langfuse keys; rebuild the index only after changing data or the embedding model with `uv run --env-file .env python -m backend.adapters.retrieval.build`; chat with `uv run --env-file .env python -m backend.chat "How does Hack and Slash work?"` (add `--roll --modifier 1` to roll).

## Suggested Story Breakdown

1. **OpenRouter LLM adapter, cost field, rulebook repository.** Add the `openai` dependency, the `LLMResponse.cost_usd` change, `openrouter.py` (chat client and factory), `json_rulebook.py`, `adapter_helpers.py` (HTTP parts), `test_adapters_openrouter.py` (chat tests), `test_adapters_rulebook.py`, the `test_ports.py` addition and the layering tests. Depends on specs 005 and 006.
2. **Chunking, BM25, index artifact and build CLI.** Add the `numpy` dependency, `OpenRouterEmbedder`, `retrieval/{chunking,embedder,bm25,index,build}.py`, `FakeEmbedder` and `mini_normalized`, with tests in `test_adapters_chunking.py`, `test_adapters_bm25.py`, `test_adapters_index.py` and the embedder tests. Verify by checking the chunk statistics printed for the committed data. If a key is available, build and commit `data/index/`. Depends on 1.
3. **Hybrid retriever.** `retrieval/hybrid.py` and `test_adapters_hybrid.py`. Depends on 2.
4. **Langfuse tracer and null tracer.** Add the `langfuse` dependency, `langfuse_tracer.py`, `null_tracer.py`, `test_adapters_langfuse.py`, and the tracing ADR. Independent of 2–3; depends on 1 (cost field).
5. **Composition root, chat CLI and docs.** `composition.py`, `chat.py`, `.env.example`, `test_composition.py`, the provider and retrieval ADRs, the architecture section and the README subsection. Then the owner smoke run (*Success Criteria*, owner items). Depends on 1–4.

## Success Criteria

Automated (implementer):
- [ ] Every test in *Testing* exists and passes with `uv run pytest` with no env vars set and no network. The `committed_*` tests may skip only for the stated missing-artifact reasons.
- [ ] `uv run ruff format --check .`, `uv run ruff check .` and `uv run pyright` exit 0.
- [ ] `[project].dependencies` gains exactly `openai`, `langfuse` and `numpy`, and `uv sync --locked` succeeds.
- [ ] `test_end_to_end_rules_turn_with_real_adapters` and `test_end_to_end_move_turn_with_roll` pass. They show the real adapters wire into the spec 006 graph and export spans with model, tokens and cost.
- [ ] Spec 006's test suite passes unmodified apart from the one additive `test_ports.py` case.
- [ ] `docs/decisions.md` has the three ADRs; `docs/architecture.md` and `README.md` have the new sections; `.env.example` has the new keys.

Owner verification (needs real keys; milestone 6 acceptance):
- [ ] `uv run --env-file .env python -m backend.adapters.retrieval.build` exits 0. `data/index/` is committed, and `test_committed_index_is_fresh` then runs and passes (no skip).
- [ ] `uv run --env-file .env python -m backend.chat "How does Hack and Slash work?"` exits 0 and prints a `rules_answer` with at least one citation.
- [ ] `uv run --env-file .env python -m backend.chat "I swing my sword at the goblin" --roll --modifier 1` exits 0 and prints a move card with a roll.
- [ ] In Langfuse, both printed `trace_id`s show a `chat_turn` trace with the CLI's `session_id`, one span per executed node, and generations showing model, input/output tokens and a non-zero cost.

## Future Considerations

- Trace the query-embedding call as a Langfuse generation (its cost is about $0.0000006 per query, so it is omitted now).
- Light stemming or plural folding in the BM25 tokenizer if spec 009 recall shows term-form misses (D6).
- Expose `GraphSettings`, `CANDIDATES`, `RRF_K` and `MAX_CHUNK_CHARS` to the spec 009 eval config for spec 010 tuning.
- OpenRouter attribution headers (`HTTP-Referer`, `X-Title`) once the public URL exists (spec 011).
- A CI step that warns when `data/normalized/` changes in a PR without a matching `data/index/` change (the freshness test already fails; this would only improve the message).
