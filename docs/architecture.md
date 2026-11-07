# Architecture

## Assistant graph

The assistant turns one user message into one structured reply (`TurnResult`) through a
LangGraph `StateGraph` compiled once by `backend.graph.builder.build_assistant` (see
ADR-011). Nodes are plain `async` functions closing over `GraphDeps` (the `LLMClient`,
`Retriever`, `Tracer` and `RulebookRepository` ports, plus a `RandomSource` and a clock);
LangGraph itself is imported only in `backend/graph/builder.py`. Every node is wrapped in
`traced`, which records one `NodeTrace` before returning; every LLM call goes through
`call_llm`, which records one `GenerationTrace` or, on a `PortError`, a `port_error`
`TraceEvent` and the fixed error reply.

```
TurnInput(message, session_id, trace_id, roll_requested, modifier)
   │  Assistant.run()  (validates input, ainvoke, builds TurnResult)
   ▼
 router ──LLM(router)──┬─ rules_question ───▶ retrieve ──Retriever── no chunks ─▶ [reply: rules_not_found] ─▶ END
                       │                        │ chunks
                       │                        ▼
                       │                  answer_with_citations ──LLM(answer)
                       │                        ▼
                       │                  citation_validator (code) ─▶ [rules_answer | rules_not_found] ─▶ END
                       │
                       ├─ action_description ─▶ classify_move ──LLM(classifier), candidates from RulebookRepository
                       │                        ├─ confidence < threshold ─▶ clarify (template) ─▶ END
                       │                        ├─ "no_move" ─────────────▶ no_move (copy) ─▶ END
                       │                        └─ move ─▶ explain ──LLM(answer)
                       │                                   ├─ roll_requested and move rolled ─▶ roll (domain.dice) ─▶ outcome (domain.outcome) ─▶ END
                       │                                   └─ otherwise ─▶ END
                       └─ out_of_scope ───────▶ out_of_scope (copy) ─▶ END

 Any node: PortError or invalid LLM output ─▶ [reply: error] ─▶ END   (every conditional edge checks "reply" first)
 Every node: Tracer.record_node; every LLM call: Tracer.record_generation; signals: Tracer.record_event
```

### Nodes

**`router`** reads the turn's message and calls the LLM (role `router`, temperature `0.0`,
JSON-Schema-constrained) to classify it into `rules_question`, `action_description` or
`out_of_scope`. It writes `intent` and `router_confidence` to the state; an unparseable
response writes the fixed error reply instead and traces `llm_output_invalid`.

**`out_of_scope`** reads nothing beyond reaching this node and calls no port besides the
tracer. It writes the fixed `out_of_scope` reply.

**`retrieve`** reads the turn's message and calls `Retriever.retrieve(message, retrieval_k)`.
It writes the retrieved `chunks`; an empty result writes the `rules_not_found` reply directly,
skipping the answer LLM call entirely.

**`answer_with_citations`** reads the message and the retrieved `chunks` and calls the LLM
(role `answer`) with each chunk rendered as `[[section_id]] title\ntext`. It writes the raw
`draft_answer` text, which still carries unvalidated `[[section_id]]` markers.

**`citation_validator`** reads `draft_answer` and the retrieved `chunks`' ids and runs the
deterministic `check_citations` (no port call). It writes the final `rules_answer` reply (with
one `Citation` per valid marker, in first-appearance order) or, if no marker survives,
`rules_not_found` with the closest retrieved sections as citations; stripped or missing
citations are traced as `citations_stripped` / `no_valid_citation`.

**`classify_move`** reads the message and the candidate moves (`RulebookRepository.list_moves()`
filtered to `basic`/`special`) and calls the LLM (role `classifier`, JSON-Schema-constrained).
It writes `candidates`, the normalised `classification` and, for a matched move, `move` and
`roll_stat`; an unknown `move_id` or unknown `alternatives` are corrected deterministically and
traced (`classifier_unknown_move`, `classifier_alternatives_stripped`,
`classifier_stat_overridden`).

**`clarify`** reads the `classification` and calls no LLM. It writes the `clarification`
reply, a deterministic template built from up to three candidate names and triggers, and
traces `clarification_requested`.

**`no_move`** reads the `classification`'s rationale and calls no LLM. It writes the `no_move`
reply (fixed copy plus the rationale, plus a "nothing to roll" sentence when the turn asked for
a roll).

**`explain`** reads the matched `move`, `roll_stat` and the classifier's rationale and calls
the LLM (role `answer`) to explain, in prose, why the move triggered and how it is rolled
(never the outcome bands or any dice result). It writes the `move` reply with a `MoveCard`
quoting the move's `outcomes` verbatim; an empty explanation writes the error reply instead.

**`roll`** reads the turn's `modifier` and calls `backend.domain.dice.roll` with the injected
`RandomSource` — never the LLM. It writes the resulting `Roll` to the state.

**`outcome`** reads the `move`, the `roll` and the existing `move` reply and calls
`backend.domain.outcome.resolve_outcome` when a modifier was given (writing `MoveCard.outcome`
and appending `roll_text_with_modifier` to the reply text) or computes
`MoveCard.bands_by_modifier` for every ability modifier −3…+3 when it wasn't (appending
`roll_text_without_modifier`). It calls no port beyond the tracer.

### Reply kinds

| `Reply.kind` | When | Citations | Move card |
|--------------|------|-----------|-----------|
| `rules_answer` | A rules question was answered with at least one valid citation. | One `Citation` per valid marker, in first-appearance order. | — |
| `rules_not_found` | Retrieval returned nothing, or no citation in the answer survived validation. | Empty, or the closest `closest_sections_limit` retrieved sections. | — |
| `move` | A move was classified with confidence at or above `clarify_threshold` and matched a candidate. | — | `MoveCard` with the move's own `outcomes`, plus `roll`/`outcome`/`bands_by_modifier` when the turn rolled. |
| `no_move` | The classifier decided no move triggers, at or above `clarify_threshold`. | — | — |
| `clarification` | Classifier confidence was below `clarify_threshold`, for any `move_id` including `no_move`. | — | — |
| `out_of_scope` | The router decided the message isn't a Dungeon World rules question or action. | — | — |
| `error` | A port raised `PortError`, or an LLM response failed structured-output validation. | — | — |

## Adapters and composition root

`backend/composition.py` is the composition root: the only module (besides `backend/chat.py`)
that imports both `backend/adapters/**` and `backend/graph/**`. `Settings.from_env(environ)`
reads every environment variable exactly once, collecting every problem into a single
`ConfigError` rather than failing on the first one; adapters themselves never read `os.environ`.
`build_runtime(settings, ...)` loads the index and rulebook, builds one real adapter per spec
006 port, wires them into `build_assistant`, and returns a `Runtime` whose `aclose()` flushes
traces and closes the HTTP clients exactly once.

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

| Port | Adapter | Library | Key behaviour |
|------|---------|---------|----------------|
| `LLMClient` | `OpenRouterLLMClient` (`backend/adapters/openrouter.py`) | `openai` (`AsyncOpenAI`, OpenRouter-compatible endpoint) | Structured requests force `response_format`/`provider.require_parameters`; every request asks for `usage.include` so `LLMResponse.cost_usd` is filled from the provider-reported cost. Failures become `PortError`, never leaking the key. |
| `Retriever` | `HybridRetriever` (`backend/adapters/retrieval/hybrid.py`) | `numpy` (vectors) + in-house `bm25.py` | Fuses the top-30 cosine hits and top-30 BM25 hits by Reciprocal Rank Fusion, deduplicates by `section_id`, cuts to `k`. Reads a committed, offline-built index (`data/index/`); embeds the query through `OpenRouterEmbedder`. |
| `Tracer` | `LangfuseTracer` (`backend/adapters/langfuse_tracer.py`) / `NullTracer` (`backend/adapters/null_tracer.py`) | `langfuse` (OpenTelemetry-based) | Records one observation per node/generation/event, grouped into one `chat_turn` Langfuse trace per `session_id`, carrying model, tokens, cost and latency. Every call is wrapped so it never raises or blocks; `NullTracer` is used locally when no Langfuse keys are configured. |
| `RulebookRepository` | `JsonRulebookRepository` (`backend/adapters/json_rulebook.py`) | stdlib `json` | Loads only `moves.json` via spec 005's `move_from_dict`; sections are read by the retriever's own index, not by this repository. |

The index build CLI (`python -m backend.adapters.retrieval.build`) is the only piece that needs
`OPENROUTER_API_KEY` at offline time; it chunks the committed normalized data
(`retrieval/chunking.py`), embeds each chunk's index text, and writes the three index files only
after every embedding batch has succeeded. `python -m backend.chat` is the local verification
path for milestone 6: it builds a `Runtime`, runs one turn, prints the reply, citations or move
card and the trace/session ids, then flushes Langfuse traces before exiting.
