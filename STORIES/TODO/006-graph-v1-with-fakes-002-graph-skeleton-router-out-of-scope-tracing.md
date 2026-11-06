# 006-graph-v1-with-fakes-002-graph-skeleton-router-out-of-scope-tracing

**Spec:** STORIES/SPECS/006-graph-v1-with-fakes.md

**As a** Dungeon World player
**I want** the assistant to classify my message's intent and answer off-topic messages with a fixed, helpful reply, failing safely with an error reply when the LLM misbehaves
**So that** I am steered to what the assistant can do, and every turn is traced for later evaluation

## Acceptance Criteria

```gherkin
Scenario: Out-of-scope message gets fixed copy with no further calls
  Given the router LLM returns intent "out_of_scope"
  When Assistant.run is called with a valid TurnInput
  Then the reply is Reply(kind="out_of_scope", text=OUT_OF_SCOPE_TEXT)
  And exactly one LLM request (role "router") was made
  And the retriever was not called and classification is None

Scenario: Router request parameters
  When the router node runs
  Then its LLMRequest has role "router", temperature 0.0, max_tokens 100, schema_name "router_decision"
  And its user prompt wraps the message in <user_message> delimiters

Scenario: Invalid router output ends the turn with the error reply
  Given the router LLM returns "not json"
  When the turn runs
  Then the reply kind is "error" with text ERROR_TEXT
  And a "llm_output_invalid" event is traced and intent is None
  And the router NodeTrace attributes are exactly {"error": True}

Scenario: Router port failure ends the turn with the error reply
  Given the router LLM raises PortError("timeout")
  When the turn runs
  Then the reply kind is "error" and a "port_error" event with port "llm" is traced

Scenario: Router output parsing is deterministic
  Given router LLM text
  When parse_router_output is called
  Then each of the three intents parses with its confidence, extra keys are ignored
  And non-JSON, a JSON array, a missing confidence, an unknown intent, confidence 1.2 or confidence true raise ValueError

Scenario: Invalid turn input is rejected before any node runs
  Given a TurnInput with an empty message, blank session_id, modifier 11 or modifier True
  Then a ValueError is raised
  And modifiers -10 and 10 are accepted

Scenario: Settings validation and defaults
  Given GraphSettings with retrieval_k 0 or clarify_threshold 1.5
  Then a ValueError is raised
  And the defaults equal the D25 values

Scenario: Graph finishing without a reply is a bug
  Given an Assistant built over a graph whose single node returns {}
  When run is called
  Then RuntimeError("graph finished without a reply") is raised

Scenario: Every executed node is traced with injected-clock latency
  Given the out-of-scope path
  When the turn runs
  Then tracer node names are ["router", "out_of_scope"]
  And the out_of_scope node latency_ms is approx 10.0 and all latencies are positive and finite
  And every node, generation and event carries trace_id "t1" and session_id "s1"

Scenario: LangGraph is confined to builder.py
  When the graph layering AST scan runs
  Then every backend/graph/*.py imports only the allow-listed modules and only builder.py imports langgraph.*
```

## Technical Notes

Implements (per Suggested Story Breakdown item 2):
- Assumptions & Decisions → D1 (`uv add langgraph`), D2, D5, D11, D17, D18, D20, D23, D25.
- Configuration → `pyproject.toml` / `uv.lock` change.
- Data Model → `backend/graph/state.py` (all types incl. `GraphState`), `backend/graph/deps.py`, `backend/graph/llm_outputs.py` (all types incl. `MoveClassification` and `NO_MOVE`; `router_schema`, `parse_router_output` only — classifier schema/parser come in story 004), `backend/graph/builder.py` (`Assistant`, `build_assistant`, `_assistant_from_compiled`).
- Graph Behaviour → *Wiring* (`START → router`, `out_of_scope → END`, router conditional; the `rules_question` and `action_description` intents are temporarily routed to the error reply until stories 003/004 wire them), `Assistant.run`; *Router* (`router`, `out_of_scope`); *Tracing* (`traced`, `call_llm`, `llm_output_invalid`, `port_error` events, router node attributes, error-node attributes); *Prompts* → `ROUTER_SYSTEM` row and the `<user_message>` wrapping; *JSON Schemas* → `router_schema()`.
- User-Facing Copy → `OUT_OF_SCOPE_TEXT`, `ERROR_TEXT` and the error-reply shape (`replies.py` is created here; later stories add their copy).
- Validation Rules → `TurnInput`, `GraphSettings`, Router output rows.
- Testing → `backend/tests/graph_helpers.py` (as specified, including the fake clock).
- Files: `pyproject.toml`, `uv.lock`, `backend/graph/{state,deps,llm_outputs,prompts,replies,tracing,router,builder}.py`, `backend/tests/graph_helpers.py`, `backend/tests/test_graph_inputs.py`, `backend/tests/test_graph_router.py`, `backend/tests/test_graph_llm_outputs.py`, `backend/tests/test_graph_tracing.py`, `backend/tests/test_graph_layering.py`.
- Open risk (a): targeted `# pyright: ignore[...]` allowed only in `builder.py`.

## Tests

- `test_graph_inputs.py`: `test_turn_input_validation`, `test_graph_settings_validation`, `test_run_without_reply_raises`, `test_compiled_graph_has_no_checkpointer`.
- `test_graph_llm_outputs.py`: `test_parse_router_output_valid`, `test_parse_router_output_invalid`, `test_parse_router_ignores_extra_keys`, `test_router_schema_shape`.
- `test_graph_router.py`: `test_out_of_scope_reply_without_further_calls`, `test_router_request_parameters`, `test_router_invalid_output_returns_error`, `test_router_port_error_returns_error`.
- `test_graph_tracing.py`: `test_every_executed_node_is_traced` (out_of_scope case), `test_trace_ids_propagate`, `test_latency_from_injected_clock`, `test_error_node_traced`.
- `test_graph_layering.py`: `test_graph_imports_allow_list`.

**Priority:** Critical
**Dependencies:** 006-graph-v1-with-fakes-001-ports-fakes-and-test-guard.md
