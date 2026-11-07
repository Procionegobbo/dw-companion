# 007-real-adapters-and-tracing-004-hybrid-retriever

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** player asking a rules question
**I want** retrieval that fuses semantic similarity with exact keyword matches
**So that** the answer is grounded in the most relevant distinct rules sections, even for exact game terms

## Acceptance Criteria

```gherkin
Scenario: At most k distinct sections
  Given an index built in tmp_path with FakeEmbedder
  When retrieve(query, k=3) runs
  Then at most 3 results are returned, with distinct section_id

Scenario: Split sections are deduplicated
  When a query matches several parts of the oversized section
  Then that section_id appears once, with the best-ranked part's text

Scenario: BM25 rescues an exact term
  Given the query vector equals the stored vector of the volley chunk
  When the query is "last breath"
  Then moves/last-breath ranks first, ahead of volley

Scenario: RRF with chunk-order tie-break
  Given a two-chunk corpus where A is vector #1/BM25 #2 and B is vector #2/BM25 #1
  Then both score exactly 1/61 + 1/62 and A (lower chunk index) comes first

Scenario: Input and error handling
  When the query is "  "
  Then [] is returned and the embedder is not called
  When the embedder raises
  Then PortError propagates
  When k = 0
  Then ValueError is raised

Scenario: Results honour the Retriever contract
  Then each result's type is "section" or "move", anchor_url follows the URL contract,
       and scores are finite and non-increasing
  And HybridRetriever is assignable to the Retriever protocol

Scenario: Adapter layering
  Then no file under backend/adapters/ imports backend.graph or backend.api,
       and the scan covered openrouter.py and retrieval/hybrid.py
  And openai, langfuse, numpy, httpx2 and opentelemetry are imported only under
      backend/adapters/, backend/composition.py and backend/tests/
```

## Technical Notes

- Assumptions & Decisions → D7 (RRF fusion, dedup by `section_id`).
- Configuration → Constants `CANDIDATES`, `RRF_K` (`hybrid.py`).
- Data Model → `HybridRetriever`.
- Adapter Behaviour → Hybrid retriever (all steps, including the zero-norm query `PortError`).
- Validation Rules → `HybridRetriever.retrieve` row.
- Architecture / Design Overview → Layering paragraph (enforced by `test_adapters_layering.py`).
- Files: `backend/adapters/retrieval/hybrid.py`, `backend/tests/adapter_helpers.py` (add `VectorStubEmbedder`, `ScriptedEmbedder`), `backend/tests/test_adapters_hybrid.py`, `backend/tests/test_adapters_layering.py`.

## Tests

`test_adapters_hybrid.py`: `test_returns_at_most_k_distinct_sections`, `test_split_section_appears_once`, `test_bm25_rescues_exact_term`, `test_rrf_order`, `test_empty_query_no_embedding_call`, `test_embedder_error_is_port_error`, `test_k_must_be_positive`, `test_results_are_valid_retrieved_chunks`, `test_satisfies_retriever_protocol`.

`test_adapters_layering.py`: `test_adapters_do_not_import_graph_or_api`, `test_vendor_sdks_confined_to_adapters`.

**Priority:** High
**Dependencies:** 007-real-adapters-and-tracing-002-chunking-and-bm25.md, 007-real-adapters-and-tracing-003-embedder-index-and-build-cli.md
