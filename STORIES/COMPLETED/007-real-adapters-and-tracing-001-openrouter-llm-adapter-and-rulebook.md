# 007-real-adapters-and-tracing-001-openrouter-llm-adapter-and-rulebook

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** developer of the DW companion
**I want** a real OpenRouter `LLMClient` that reports provider cost, and a JSON-backed `RulebookRepository`
**So that** the spec 006 graph can call real chat models and read real moves, with the billed cost of every call available for tracing

## Acceptance Criteria

```gherkin
Scenario: LLMResponse carries an optional provider cost
  Given the spec 006 LLMResponse type
  When it is constructed with four arguments
  Then it is valid and cost_usd is None
  And cost_usd accepts None, 0.0 and 0.002
  And cost_usd = -0.01, NaN or True raises ValueError
  And every existing spec 006 test passes unmodified

Scenario: Structured chat request is serialised for OpenRouter
  Given an OpenRouterLLMClient with models {router: "m-router", classifier: ..., answer: "m-answer"}
  When a router request with a response schema is generated
  Then exactly one POST goes to /api/v1/chat/completions with "Bearer <key>" authorization
  And the body has the role's model, system then user messages, max_tokens, temperature,
      response_format json_schema (name, strict true, schema), provider.require_parameters true and usage.include true

Scenario: Unstructured chat request
  When an answer request without a schema is generated
  Then the body has no response_format and no provider, and usage is present

Scenario: Response mapping
  Given an OpenRouter response with content, model, usage tokens and usage.cost
  Then LLMResponse has text, model, input/output tokens and cost_usd from usage.cost
  And a missing usage.cost gives cost_usd None
  And null content gives text ""

Scenario: Provider failures become PortError without secrets
  When OpenRouter answers 401
  Then PortError names the exception class and status code and never contains the API key
  When OpenRouter answers 500 twice
  Then the SDK retries once (2 requests) and then PortError is raised
  When the request times out
  Then PortError names APITimeoutError
  When the response has no choices
  Then PortError is raised

Scenario: Model mapping must be complete
  When OpenRouterLLMClient is constructed without the classifier role
  Then ValueError is raised

Scenario: JSON rulebook repository
  Given a normalized directory with moves.json
  When JsonRulebookRepository.from_dir loads it
  Then list_moves returns the moves in file order and get_move finds by id
  And get_move of an unknown id returns None
  And duplicate ids raise ValueError
  And an invalid move raises ValueError whose message contains the file path
  And a non-array top level raises ValueError
```

## Technical Notes

- Prerequisites outside this spec: specs 005 and 006 implemented (ports, fakes, `move_from_dict`, no-network guard).
- Assumptions & Decisions → D11 (`cost_usd`), D12 (chat request shape, timeout, retries, `openai` dependency), D13 (models per role), D21 (mock transport testing), D22 (port errors), D24 (rulebook repository).
- Configuration → Constants (`OPENROUTER_BASE_URL`, `CHAT_TIMEOUT_S`, `EMBEDDINGS_TIMEOUT_S`, `MAX_RETRIES`); `pyproject.toml` → add `openai` only in this story.
- Data Model → `LLMResponse` (modified), `make_openrouter_client`, `OpenRouterLLMClient`, `JsonRulebookRepository`.
- Adapter Behaviour → OpenRouter (chat request body, response mapping table, failure table, constructor `ValueError`); Rulebook repository.
- Validation Rules → `LLMResponse.cost_usd`, `OpenRouterLLMClient.models`, `JsonRulebookRepository` rows.
- Impact on Existing Code → `backend/ports/llm.py`, `backend/tests/test_ports.py` (additive), `pyproject.toml`, `uv.lock`.
- Files: `backend/adapters/openrouter.py` (factory + chat client; `OpenRouterEmbedder` comes in story 003), `backend/adapters/json_rulebook.py`, `backend/tests/adapter_helpers.py` (HTTP parts only: `mock_http`, `chat_completion_json`, `RecordingHandler`), `backend/tests/test_adapters_openrouter.py`, `backend/tests/test_adapters_rulebook.py`.

## Tests

`test_ports.py`: `test_llm_response_cost_validation`.

`test_adapters_openrouter.py`: `test_chat_request_body_for_structured_call`, `test_chat_request_body_without_schema`, `test_model_selected_per_role`, `test_response_mapping_with_cost`, `test_missing_cost_is_none`, `test_null_content_becomes_empty_text`, `test_status_error_raises_port_error_without_secrets`, `test_server_error_retried_once_then_port_error`, `test_timeout_raises_port_error`, `test_no_choices_raises_port_error`, `test_missing_model_role_rejected`.

`test_adapters_rulebook.py`: `test_loads_committed_moves`, `test_get_unknown_move_returns_none`, `test_duplicate_ids_rejected`, `test_invalid_file_names_path`, `test_top_level_must_be_array`.

**Priority:** Critical
**Dependencies:** None
