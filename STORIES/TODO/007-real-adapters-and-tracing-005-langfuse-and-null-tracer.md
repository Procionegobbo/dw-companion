# 007-real-adapters-and-tracing-005-langfuse-and-null-tracer

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** project owner
**I want** every graph node, LLM generation and event exported to Langfuse with session, intent, model, tokens, cost and latency, and a no-op tracer when tracing is not configured
**So that** I can observe and cost every chat turn without tracing ever breaking or blocking a turn

## Acceptance Criteria

```gherkin
Scenario: Node span exported
  Given a memory tracer with an in-memory span exporter
  When record_node(NodeTrace("ab"*16, "s1", "retrieve", 12.5, {"count": 6})) is called and flushed
  Then one span named "retrieve" is exported with that trace id, session.id "s1", trace name "chat_turn",
       metadata containing count and latency_ms, and a duration of 12.5 ms within 1 ms

Scenario: Non-hex trace id
  When trace_id is "t1"
  Then the span trace id is Langfuse.create_trace_id(seed="t1")

Scenario: Generation with model, usage and cost
  When a GenerationTrace with model "openai/x", tokens 12/7 and cost_usd 0.00042 is recorded
  Then a generation observation has model openai/x, usage {"input": 12, "output": 7},
       cost {"total": 0.00042}, and model parameters containing max_tokens
  And with cost_usd None there is no cost attribute

Scenario: Intent propagation
  When a router node with intent "rules_question" is followed by a retrieve node on the same trace
  Then both spans carry tag "intent:rules_question"
  And a node on a different trace id has no intent tag

Scenario: Levels
  Then event port_error has level ERROR, citations_stripped WARNING, clarification_requested DEFAULT
  And a node with attributes {"error": True} has level ERROR

Scenario: Tracer never raises
  Given start_observation and create_event raise RuntimeError
  Then every record_* returns None and a WARNING containing RuntimeError is logged

Scenario: Null tracer
  Then every NullTracer method returns None
  And both LangfuseTracer and NullTracer are assignable to the Tracer protocol
```

## Technical Notes

- Assumptions & Decisions → D14 (`langfuse` dependency, wrapped SDK calls, async export), D15 (trace id rule, `propagate_attributes`), D16 (intent memory, bounded at 1,024), D17 (span timing), D11 (cost sent as `cost_details`).
- Configuration → `pyproject.toml` → add `langfuse` in this story.
- Data Model → `LangfuseTracer`, `make_langfuse_tracer`, `NullTracer`.
- Adapter Behaviour → Langfuse tracer (observation mapping table, event levels table, `flush`/`close`, WARNING log format on logger `backend.adapters.langfuse`).
- Open risks → b (behaviours asserted by tests; unique public key per test client).
- Authorization & Security → Privacy.
- Documentation → ADR "Tracing: Langfuse adapter" in `docs/decisions.md` (next free ADR number, D25).
- Files: `backend/adapters/langfuse_tracer.py`, `backend/adapters/null_tracer.py`, `backend/tests/adapter_helpers.py` (add `memory_tracer`), `backend/tests/test_adapters_langfuse.py`, `docs/decisions.md`.

## Tests

`test_adapters_langfuse.py`: `test_node_span_exported`, `test_non_hex_trace_id_mapped_deterministically`, `test_generation_has_model_usage_and_cost`, `test_generation_without_cost_has_no_cost_details`, `test_intent_propagates_after_router`, `test_event_levels`, `test_error_node_level`, `test_tracer_never_raises`, `test_null_tracer_accepts_everything`, `test_tracers_satisfy_protocol`.

**Priority:** High
**Dependencies:** 007-real-adapters-and-tracing-001-openrouter-llm-adapter-and-rulebook.md
