# 008-api-and-chat-widget-001-graph-streaming-and-cost-metering

**Spec:** STORIES/SPECS/008-api-and-chat-widget.md

**Stack:** backend (`python-feature-builder`)

**As a** developer building the chat API
**I want** the assistant to stream node-level progress and the runtime to report the cost of every completed LLM call
**So that** the API can send live progress over SSE and enforce a daily spend cap without the graph or adapters knowing about budgets

## Acceptance Criteria

```gherkin
Feature: Assistant.stream and LLM cost metering

  Scenario: Stream yields executed nodes then exactly one result
    Given an assistant built over spec 006 fakes scripted for a given path (out_of_scope, rules, move+roll, clarify, no_move)
    When I iterate Assistant.stream(turn)
    Then I receive one NodeCompleted per executed node, in execution order, matching spec 006's traced node list for that path
    And the last event is a TurnResult, and it is the only TurnResult

  Scenario: Stream result equals run result
    Given two assistants with identical scripted fakes
    When one runs Assistant.run(turn) and the other iterates Assistant.stream(turn)
    Then the streamed TurnResult equals the run TurnResult on every path

  Scenario: Graph error reply still completes the stream
    Given the router LLM call raises PortError
    When I iterate Assistant.stream(turn)
    Then I receive NodeCompleted("router") followed by a TurnResult whose reply kind is "error"

  Scenario: Graph finishing without a reply
    Given an assistant built with _assistant_from_compiled over a graph that returns {}
    When I iterate Assistant.stream(turn)
    Then RuntimeError("graph finished without a reply") is raised during iteration

  Scenario: NodeCompleted validation
    When I construct NodeCompleted with an empty node name
    Then ValueError is raised

  Scenario: Assistant.run is unchanged
    Given the existing spec 006 test suite
    When the suite runs after this change
    Then every spec 006 test passes unmodified

  Scenario: Metered client records provider cost
    Given an inner LLM client whose response has cost_usd 0.002
    When MeteredLLMClient.generate is awaited
    Then on_cost is called once with 0.002
    And the returned response is the same object the inner client returned
    And the inner client received the same request object

  Scenario: Missing cost counts the fallback and warns once
    Given an inner LLM client whose responses have cost_usd None
    When MeteredLLMClient.generate is awaited twice
    Then on_cost receives 0.01 and 0.01
    And exactly one WARNING is logged on logger backend.adapters.metered_llm

  Scenario: Failed calls record nothing
    Given an inner LLM client that raises PortError
    When MeteredLLMClient.generate is awaited
    Then the PortError propagates
    And on_cost is never called

  Scenario: build_runtime meters chat LLM cost when a hook is given
    Given the spec 007 end-to-end rules turn setup with mock transport cost 0.00042
    And build_runtime is called with on_llm_cost=costs.append
    When the rules turn runs
    Then costs equals [0.00042, 0.00042] (router and answer)

  Scenario: build_runtime without the hook is unchanged
    Given build_runtime is called without on_llm_cost
    When the spec 007 tests and backend/chat.py run
    Then their behaviour is identical and every spec 007 test passes unmodified
```

## Technical Notes

Implements, from the spec:
- **Assumptions & Decisions → D4** (`Assistant.stream` via LangGraph `astream` with `stream_mode=["updates", "values"]`, confined to `builder.py`) and **D12** (cost captured by `MeteredLLMClient`, fallback cost, failed calls count nothing; embeddings not counted).
- **Data Model → Backend types**: `NodeCompleted` / `AssistantEvent` (`backend/graph/state.py`), `Assistant.stream` (`backend/graph/builder.py`), `MeteredLLMClient` + `FALLBACK_CALL_COST_USD` (`backend/adapters/metered_llm.py`), `build_runtime(..., on_llm_cost=None)` (`backend/composition.py`).
- **API Behaviour → `MeteredLLMClient` and composition** and **API Behaviour → `Assistant.stream` (`builder.py`)**.
- **Validation Rules → `NodeCompleted` row.**
- **Impact on Existing Code** rows: `backend/graph/state.py`, `backend/graph/builder.py` (state-to-`TurnResult` conversion extracted into a private helper shared by `run` and `stream`; `run`, `compiled`, `_assistant_from_compiled` unchanged), `backend/adapters/metered_llm.py` (imports only `backend.ports.*`, `logging`, `math`, stdlib typing), `backend/composition.py`, `backend/tests/test_composition.py` (additive).
- **Configuration → Constants**: `FALLBACK_CALL_COST_USD = 0.01`.
- Open risk (c) (LangGraph `astream` tuple shape) is caught by `test_stream_result_equals_run_result`.

Files: `backend/graph/state.py`, `backend/graph/builder.py`, `backend/adapters/metered_llm.py`, `backend/composition.py`, `backend/tests/test_graph_stream.py`, `backend/tests/test_adapters_metered_llm.py`, `backend/tests/test_composition.py`.

No new dependencies in this story.

## Tests

From **Testing**:
- `backend/tests/test_graph_stream.py`: `test_stream_yields_nodes_then_result` (parametrized over the five paths), `test_stream_result_equals_run_result`, `test_stream_error_reply_still_completes`, `test_stream_without_reply_raises`, `test_node_completed_validation`.
- `backend/tests/test_adapters_metered_llm.py`: `test_records_provider_cost`, `test_missing_cost_counts_fallback_and_warns_once`, `test_port_error_records_nothing`, `test_request_passed_through_unchanged`, `test_satisfies_llm_client_protocol`.
- `backend/tests/test_composition.py` (additive): `test_build_runtime_meters_llm_cost`.

**Priority:** Critical
**Dependencies:** None (requires specs 006 and 007 to be implemented)
