# 009-evals-runner-and-first-reports-003-backend-tracing-pricing-and-judge-seams

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** developer of the eval harness
**I want** additive seams in the spec 007 composition root and adapters (tracer tee, trace options, graph settings injection, OpenRouter prices, judge client)
**So that** evals can trace with config metadata, tap per-call cost, and fetch prices without importing any vendor SDK and without changing chat behaviour

## Acceptance Criteria

```gherkin
Feature: Additive backend seams for evals

  Scenario: TeeTracer forwards every record in order
    Given a TeeTracer over two recording tracers
    When each record_* method is called
    Then both delegates receive every record in the same order

  Scenario: TeeTracer swallows and logs a delegate failure
    Given a TeeTracer whose first delegate raises
    When a record is sent
    Then the second delegate still receives it
    And exactly one WARNING "tracer delegate failed: <ClassName>" is logged on backend.adapters.tee_tracer
    And no exception escapes

  Scenario: TeeTracer needs at least two delegates
    When TeeTracer is constructed with fewer than 2 tracers
    Then ValueError is raised

  Scenario: LangfuseTracer defaults are unchanged
    Given a LangfuseTracer built with default options
    Then observations have trace name "chat_turn" and no extra metadata or tags

  Scenario: Static metadata and tags on every observation
    Given a LangfuseTracer with static_metadata and static_tags
    When a turn is traced through the router
    Then every observation carries the static metadata and tags
    And after the router they are merged with "intent" and "intent:<x>"

  Scenario: Custom trace name
    Given a LangfuseTracer with trace_name "eval_turn"
    Then observations use trace name "eval_turn"

  Scenario: Prices are parsed from OpenRouter model_extra
    Given a /models response with string pricing.prompt and pricing.completion
    When fetch_model_prices is called for those ids
    Then a ModelPrice with float per-token prices is returned per id

  Scenario: Missing model is a PortError
    When fetch_model_prices asks for an id absent from /models
    Then PortError "openrouter pricing unavailable for <id>" is raised

  Scenario Outline: Invalid pricing is a PortError
    Given a model whose pricing is <bad>
    When fetch_model_prices is called
    Then PortError is raised

    Examples:
      | bad              |
      | missing          |
      | "abc"            |
      | "-1"             |

  Scenario: HTTP failure is a PortError without the key
    Given /models returns status 500
    When fetch_model_prices is called
    Then PortError mentions "(status 500)" and does not contain the API key

  Scenario: build_runtime defaults unchanged
    When build_runtime is called without the new arguments
    Then Runtime.tracer is the primary tracer and GraphSettings() is used

  Scenario: Graph settings are injected
    Given the spec 007 mock-transport rules-turn setup and GraphSettings(retrieval_k=3)
    When a rules turn runs
    Then TurnResult.retrieved_section_ids has exactly 3 ids

  Scenario: Tracer tap receives records
    Given build_runtime with a tracer_tap
    When a turn runs
    Then the tap receives the turn's records and Runtime.tracer is TeeTracer(primary, tap)

  Scenario Outline: TraceOptions validation
    When TraceOptions is constructed with <violation>
    Then ValueError is raised

    Examples:
      | violation                                  |
      | a trace_name not matching ^[a-z_]+$        |
      | a metadata key not matching ^[a-z_]+$      |
      | the metadata key "intent"                  |
      | a metadata value over 200 characters       |
      | an empty tag                               |
      | a tag over 200 characters                  |
      | a tag starting with "intent:"              |

  Scenario: Eval support builds the judge client and prices
    When build_eval_support is called with a judge model and price ids
    Then the judge's request goes to the judge model
    And prices are parsed
    And aclose closes the client exactly once even if called twice
```

## Technical Notes

- **D8** (a)–(f), **D7** (trace name/metadata/tags), **D10** (pricing source).
- **Data Model → Backend additions**: `backend/composition.py` (`HttpClientSeam`, `SpanExporterSeam`, `TraceOptions`, `Runtime.tracer`, new `build_runtime` keyword arguments, `EvalSupport`, `build_eval_support`), `backend/adapters/langfuse_tracer.py` (`trace_name`, `static_metadata`, `static_tags`), `backend/adapters/tee_tracer.py` (`TeeTracer`), `backend/adapters/openrouter.py` (`ModelPrice`, `fetch_model_prices`).
- **Tracing** — `TraceOptions` validation, the `LangfuseTracer` `propagate_attributes` change, `build_runtime` tap/tee wiring (`close_callback` still closes only the primary), `TeeTracer` logging contract.
- **Budget Guard → `fetch_model_prices`** paragraph (exact id match, `model_extra`, PortError messages). Open risk (b).
- **Validation Rules →** `TraceOptions`, `ModelPrice`, `TeeTracer` rows.
- **Impact on Existing Code →** the `backend/` rows plus `backend/tests/adapter_helpers.py` (`memory_exporter()`, `models_json(...)`). All changes are additive; existing spec 007 tests pass unmodified; `backend/chat.py` is unchanged. Open risk (e): keep spec 008's `on_llm_cost` argument if it already landed.
- Independent of stories 001–002.

## Tests

- `backend/tests/test_adapters_tee_tracer.py`: `test_tee_forwards_all_records_in_order`, `test_tee_swallows_and_logs_delegate_failure`, `test_tee_requires_two_delegates`.
- `backend/tests/test_adapters_langfuse.py`: `test_default_options_unchanged`, `test_static_metadata_and_tags_on_every_observation`, `test_custom_trace_name`.
- `backend/tests/test_adapters_openrouter.py`: `test_fetch_model_prices_parses_extra_pricing`, `test_fetch_model_prices_missing_model_port_error`, `test_fetch_model_prices_invalid_pricing_port_error`, `test_fetch_model_prices_http_error_port_error`.
- `backend/tests/test_composition.py`: `test_build_runtime_defaults_unchanged`, `test_build_runtime_graph_settings_applied`, `test_build_runtime_tracer_tap_receives_records`, `test_trace_options_validation`, `test_build_eval_support_judge_and_prices`.

**Priority:** High
**Dependencies:** None
