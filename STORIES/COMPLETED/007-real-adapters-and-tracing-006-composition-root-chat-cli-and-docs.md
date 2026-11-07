# 007-real-adapters-and-tracing-006-composition-root-chat-cli-and-docs

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** developer of the DW companion
**I want** a composition root that wires the real adapters from environment variables into the assistant, and a local chat command
**So that** I can run a real chat turn end to end and see it traced in Langfuse (milestone 6)

## Acceptance Criteria

```gherkin
Scenario: Settings from env
  Given every variable is set (with surrounding whitespace)
  Then Settings has stripped values and langfuse.base_url defaults to https://cloud.langfuse.com
  Given an empty environment
  Then one ConfigError names OPENROUTER_API_KEY, MODEL_ROUTER, MODEL_CLASSIFIER, MODEL_ANSWER and MODEL_EMBEDDINGS
  And whitespace-only values count as unset
  And only one Langfuse key set raises ConfigError
  And repr(settings) contains neither secret value

Scenario: Tracing disabled without Langfuse keys
  Given both Langfuse keys are empty
  Then settings.langfuse is None and build_runtime logs a "tracing disabled" warning

Scenario: Embedding model mismatch fails at startup
  Given an index built with "fake-embed" and MODEL_EMBEDDINGS "other"
  Then build_runtime raises ConfigError mentioning both names

Scenario: .env.example declares every setting
  Then every name in ENV_VARS appears as a key in .env.example

Scenario: End-to-end rules turn with real adapters
  Given a FakeEmbedder index, mini_normalized, a mock HTTP transport and an in-memory span exporter
  When a rules question runs through build_runtime's assistant and the runtime is closed
  Then the reply is rules_answer with one citation to /rules/moves/hack-and-slash/
  And the chat requests used m-router/m-answer with max_tokens 100/700
  And spans include router, retrieve, answer_with_citations, citation_validator and two generations with usage and cost
  And every span has session.id "s1" and the given trace id

Scenario: End-to-end move turn with a roll
  Given classifier output hack-and-slash 0.9, roll_requested, modifier 1 and ScriptedRandom([4, 5])
  Then the reply is a move with a strong_hit outcome and text ending "Rolled 4 + 5 + 1 = 10: 10+."

Scenario: Chat CLI
  When chat.main(["hi"], environ={}) runs
  Then it returns 2 and stderr starts "chat: error: invalid configuration:"
  Given build_runtime returns a runtime over spec 006 fakes with a scripted rules answer
  Then it returns 0 and prints the reply, "Citations:", "- Hack and Slash: /rules/moves/hack-and-slash/"
       and a final line "kind=rules_answer intent=rules_question trace_id=<32 hex> session_id=<32 hex>"
  Given the fake LLM raises PortError
  Then it returns 1
```

## Technical Notes

- Assumptions & Decisions → D18 (optional tracing), D19 (composition root, no `.env` loader), D20 (chat CLI), D21 (two end-to-end tests with the three seams), D23 (loud startup failures), D26 (`GraphSettings()` defaults), D25 (ADR numbering).
- Configuration → Environment variables table; `.env.example` (one comment above `MODEL_EMBEDDINGS=`, appended block); Constants `DEFAULT_INDEX_DIR`, `DEFAULT_NORMALIZED_DIR`, `REPO_ROOT`.
- Data Model → `ConfigError`, `ENV_VARS`, `LangfuseSettings`, `Settings`, `Runtime`, `build_runtime`, chat `main`.
- Composition Root and Chat CLI → all of it (error message format, the six `build_runtime` steps, CLI arguments, output format, exit codes).
- Validation Rules → `Settings.from_env`, `backend.chat --modifier`, Embedding model rows.
- Authorization & Security → Secrets.
- Documentation → ADR "Model provider: OpenRouter for chat and embeddings", ADR "Retrieval: section chunks, NumPy + in-house BM25 hybrid, committed index", `docs/architecture.md` section `## Adapters and composition root`, `README.md` subsection `### Running the assistant locally`.
- Files: `backend/composition.py`, `backend/chat.py`, `.env.example`, `backend/tests/test_composition.py`, `docs/decisions.md`, `docs/architecture.md`, `README.md`.
- After merge: the owner verification items in Success Criteria (real-key index build and commit, two CLI smoke runs, Langfuse check).

## Tests

`test_composition.py`: `test_settings_from_env_valid`, `test_settings_lists_all_missing`, `test_whitespace_counts_as_unset`, `test_langfuse_half_configured_rejected`, `test_langfuse_absent_gives_null_tracer_and_warning`, `test_settings_repr_hides_secrets`, `test_env_example_declares_every_setting`, `test_embedding_model_mismatch_rejected`, `test_end_to_end_rules_turn_with_real_adapters`, `test_end_to_end_move_turn_with_roll`, `test_chat_cli_config_error_exit_2`, `test_chat_cli_prints_reply_and_ids`, `test_chat_cli_error_reply_exit_1`.

**Priority:** Critical
**Dependencies:** 007-real-adapters-and-tracing-001-openrouter-llm-adapter-and-rulebook.md, 007-real-adapters-and-tracing-002-chunking-and-bm25.md, 007-real-adapters-and-tracing-003-embedder-index-and-build-cli.md, 007-real-adapters-and-tracing-004-hybrid-retriever.md, 007-real-adapters-and-tracing-005-langfuse-and-null-tracer.md
