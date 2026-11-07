# 007-real-adapters-and-tracing-003-embedder-index-and-build-cli

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** project owner
**I want** an OpenRouter embeddings client, a validated on-disk index artifact and a CLI that builds it
**So that** the rulebook's vector index is built offline once, committed, and loaded safely at startup

## Acceptance Criteria

```gherkin
Scenario: Embeddings are batched and ordered
  Given an OpenRouterEmbedder with batch_size 64
  When 130 texts are embedded
  Then 3 requests are sent with input sizes 64, 64, 2, encoding_format "float" and the configured model
  And returned vectors follow input order even when a response lists data in reverse index order
  And embed([]) returns [] with no request
  And a response with fewer vectors than inputs raises PortError

Scenario: Write and load round trip
  Given chunks from mini_normalized and FakeEmbedder vectors
  When write_index then load_index run on tmp_path
  Then the chunks are equal, embeddings are float32 (n, 64) with unit-norm rows,
       and the manifest model and chunks SHA-256 match
  And write_index rejects a zero vector with ValueError

Scenario: Corrupt or unsafe artifacts are rejected
  Then a one-byte edit to chunks.json raises ValueError mentioning chunks_sha256
  And embeddings.npy with one row fewer raises ValueError
  And non-finite values raise ValueError
  And a pickled object-dtype array raises ValueError
  And a missing manifest.json raises FileNotFoundError

Scenario: Build CLI succeeds
  Given build.make_embedder returns FakeEmbedder
  When build.main(["--normalized", d, "--out", o], environ with key and model) runs
  Then it returns 0, writes manifest.json, chunks.json and embeddings.npy, and prints the summary line

Scenario: Build CLI fails without writing
  When OPENROUTER_API_KEY is missing from environ
  Then it returns 2, stderr contains "OPENROUTER_API_KEY is required", and nothing is written
  When the embedder raises PortError
  Then it returns 2 and the output directory has no files

Scenario: Committed index freshness
  Given data/index/manifest.json is committed
  Then chunks_to_json(build_chunks(committed data)) equals the committed chunks.json and load_index succeeds
  Given it is absent
  Then the test skips with reason "data/index not committed yet: run python -m backend.adapters.retrieval.build with OPENROUTER_API_KEY"
```

## Technical Notes

- Assumptions & Decisions → D1 (OpenRouter embeddings, injected client), D2 (model recorded in manifest), D3 (NumPy matrix, `numpy` dependency), D4 (committed index, build CLI), D10 (`EMBED_MAX_CHARS` truncation and warning), D21 (`FakeEmbedder`).
- Configuration → Constants `EMBEDDINGS_TIMEOUT_S`, `EMBED_BATCH_SIZE`; `pyproject.toml` → add `numpy` in this story.
- Data Model → `Embedder` protocol, `OpenRouterEmbedder`, `FORMAT_VERSION`, `IndexManifest`, `LoadedIndex`, `write_index`, `load_index`, `make_embedder`, build `main`; Index artifact table (all three files).
- Adapter Behaviour → OpenRouter → `OpenRouterEmbedder.embed`; Index and build CLI (`write_index` validation, the seven ordered `load_index` checks, CLI arguments, output lines, exit codes, write-only-after-all-batches).
- Validation Rules → `IndexManifest`, Index files, `write_index`, `OpenRouterEmbedder` rows.
- Authorization & Security → Untrusted artifact loading (`allow_pickle=False`).
- Files: `backend/adapters/openrouter.py` (add `OpenRouterEmbedder`), `backend/adapters/retrieval/embedder.py`, `backend/adapters/retrieval/index.py`, `backend/adapters/retrieval/build.py`, `backend/tests/fakes/embedder.py`, `backend/tests/adapter_helpers.py` (add `embeddings_json`), `backend/tests/test_adapters_openrouter.py` (embedder tests), `backend/tests/test_adapters_index.py`.
- Verify by checking the chunk statistics the CLI prints for the committed data (Open risks → d). If an `OPENROUTER_API_KEY` is available, build and commit `data/index/`; otherwise this is the owner step in Success Criteria (Open risks → f).

## Tests

`test_adapters_openrouter.py`: `test_embedder_batches_in_order`, `test_embedder_count_mismatch_raises`, `test_embedder_empty_input_no_request`, `test_adapters_satisfy_protocols`.

`test_adapters_index.py`: `test_write_and_load_round_trip`, `test_load_rejects_tampered_chunks`, `test_load_rejects_shape_mismatch`, `test_load_rejects_non_finite`, `test_load_rejects_pickled_array`, `test_load_missing_file`, `test_write_rejects_zero_vector`, `test_build_cli_writes_index`, `test_build_cli_missing_key`, `test_build_cli_provider_failure_writes_nothing`, `test_committed_index_is_fresh`.

**Priority:** High
**Dependencies:** 007-real-adapters-and-tracing-001-openrouter-llm-adapter-and-rulebook.md, 007-real-adapters-and-tracing-002-chunking-and-bm25.md
