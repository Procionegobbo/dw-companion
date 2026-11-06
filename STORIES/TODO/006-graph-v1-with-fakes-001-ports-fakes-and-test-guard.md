# 006-graph-v1-with-fakes-001-ports-fakes-and-test-guard

**Spec:** STORIES/SPECS/006-graph-v1-with-fakes.md

**As a** backend developer
**I want** the four port protocols with validated value types, a hand-written fake per port, a pure URL helper and a no-network guard for backend tests
**So that** the assistant graph can be built and tested against stable contracts without calling any LLM, vector store, tracing service or network

## Acceptance Criteria

```gherkin
Scenario: URL helper mirrors the spec 004 URL contract
  Given a valid section id "moves/hack-and-slash"
  When section_url is called
  Then it returns "/rules/moves/hack-and-slash/"
  And move_url("hack-and-slash") returns "/moves/hack-and-slash/"

Scenario: URL helper rejects invalid ids
  Given an id such as "", "Moves", "moves/" or "a b"
  When section_url or move_url is called with it
  Then a ValueError is raised

Scenario: Port value types validate on construction
  Given an LLMRequest, LLMResponse, RetrievedChunk, NodeTrace, GenerationTrace or TraceEvent
  When it is constructed with a value violating its Validation Rules row
  Then a ValueError naming the type and field is raised
  And a value satisfying every rule constructs successfully

Scenario: Fakes satisfy their protocols
  Given FakeLLMClient, FakeRetriever, FakeTracer and FakeRulebookRepository
  When each is assigned to a variable annotated with its Protocol
  Then pyright strict reports no error

Scenario: FakeLLMClient fails loudly on an unscripted call
  Given a FakeLLMClient with no queued router responses
  When a router request is generated
  Then an AssertionError containing "unexpected router call" is raised

Scenario: FakeRetriever honours k
  Given a FakeRetriever holding 8 chunks
  When retrieve("q", 6) is awaited
  Then 6 chunks are returned and calls == [("q", 6)]

Scenario: Ports depend only on domain and stdlib
  Given every module in backend/ports/
  When the layering AST scan runs
  Then each imports only the allowed stdlib modules, backend.domain.* and backend.ports.*

Scenario: Backend tests cannot open network connections
  Given the autouse conftest guard
  When a test calls socket.create_connection(("127.0.0.1", 9))
  Then a RuntimeError mentioning "network" is raised
```

## Technical Notes

Implements:
- Assumptions & Decisions → D3 (sync/async ports), D19 (`PortError`), D21 (`domain/urls.py`), D24 (socket guard).
- Data Model → `backend/ports/errors.py`, `backend/ports/llm.py`, `backend/ports/retriever.py`, `backend/ports/tracer.py`, `backend/ports/rulebook.py`, `backend/domain/urls.py`.
- Validation Rules → `LLMRequest`, `LLMResponse`, `RetrievedChunk`, `NodeTrace`/`GenerationTrace`/`TraceEvent`, `section_url`/`move_url` rows.
- Testing → *Fakes* (`FakeLLMClient`, `FakeRetriever`, `FakeTracer`, `FakeRulebookRepository`).
- Impact on Existing Code → rows for `backend/domain/urls.py`, `backend/ports/*.py`, `backend/tests/conftest.py`, `backend/tests/fakes/*`, `backend/tests/test_domain_urls.py`, `backend/tests/test_ports.py`, `backend/tests/test_graph_layering.py` (ports scan and network-guard test only). `backend/ports/__init__.py` stays empty.

Prerequisites outside this spec: specs 001 and 005 implemented (empty `backend/ports/` package, domain types, spec 005 id patterns). No new dependency in this story.

## Tests

- `test_domain_urls.py`: `test_section_url`, `test_move_url`, `test_invalid_ids_rejected`.
- `test_ports.py`: `test_llm_request_validation`, `test_llm_response_validation`, `test_retrieved_chunk_validation`, `test_trace_records_validation`, `test_fakes_satisfy_protocols`, `test_fake_llm_fails_on_unexpected_call`, `test_fake_retriever_truncates_to_k`.
- `test_graph_layering.py`: `test_ports_import_only_domain_and_stdlib`, `test_no_network_guard_active`.

**Priority:** Critical
**Dependencies:** None
