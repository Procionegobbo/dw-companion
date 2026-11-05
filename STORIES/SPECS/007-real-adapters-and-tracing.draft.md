# 007 - Real adapters, retrieval index, and tracing

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 002 (normalized data to index), 006 (graph wired against ports).
**Reference:** `HANDOFF_dw-companion.md`, sections 4.2, 4.3, 10 (milestone 6).

## Scope

Replace the fakes from spec 006 with real adapters:

- **LLM adapter**: provider is OpenRouter (decided), OpenAI-compatible client. All model
  names come from env vars (`MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER`,
  `MODEL_EMBEDDINGS`) — never hardcoded. Router and move classifier use a small/fast/cheap
  model with structured output (JSON schema / tool call), temperature 0. Rules answers and
  move explanations use a larger model. Note: OpenRouter does not serve embeddings — resolve
  where `MODEL_EMBEDDINGS` actually comes from (a separate provider/key) and record the
  decision in `docs/decisions.md`.
- **Retrieval**: chunk by semantic section from the normalized data (never fixed token
  windows); each chunk carries `section_id`, `title`, `chapter`, `anchor_url`, `type`. Moves
  are chunks of their own, never split. Hybrid retrieval: vector similarity + BM25 keyword
  search (catches exact game terms like "Hack and Slash" better than embeddings alone).
  Index is built offline and baked into the container image (Chroma, LanceDB, or
  FAISS/NumPy) — no managed vector DB; document this trade-off in `docs/decisions.md`.
- **Tracer**: Langfuse adapter on every graph node — model, tokens, cost, latency, intent.
  No IP addresses logged; use a random session ID.
- **RulebookRepository**: real adapter loading `data/normalized/*.json`.

## Out of scope

- The FastAPI app and chat widget that will call this graph (spec 008).
- Evaluation of retrieval/answer quality (spec 009) — this spec only needs the adapters to
  work end-to-end, not to be measured yet.

## Acceptance (from handoff milestone 6)

Done when end-to-end chat works locally and traces appear in Langfuse with tokens and cost.
