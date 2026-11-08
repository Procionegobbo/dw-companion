# 009-evals-runner-and-first-reports-006-eval-cli

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner
**I want** a single `python -m evals.run` command that validates, gates on reviewed labels, checks the budget, runs the selected datasets traced in Langfuse, and writes reports
**So that** I can produce a trustworthy, cost-bounded eval report with one command once I have reviewed the labels

## Acceptance Criteria

```gherkin
Feature: Eval CLI

  # R-LABEL, entry-point enforcement
  Scenario: Unreviewed row is refused at the entry point
    Given fixture paths where rules_qa.jsonl has one row with "reviewed": false
    When main is called
    Then it returns 3
    And stderr starts with "evals: error: rules_qa.jsonl has 1 unreviewed row"
    And the services factory is never called
    And no report file is written

  Scenario: Missing reviewed key is refused
    Given a row with the "reviewed" key absent
    When main is called
    Then it returns 3 and the services factory is never called

  Scenario: A single unreviewed row blocks all datasets
    Given --dataset all, router and move_classification fully reviewed, one rules_qa row unreviewed
    When main is called
    Then it returns 3 and the services factory is never called

  Scenario: There is no override flag
    When main is called with --allow-unreviewed
    Then argparse exits with code 2

  Scenario: Committed unreviewed datasets are refused without env
    Given data/normalized/ is present and the committed datasets
    When `uv run python -m evals.run --config baseline` runs with no env
    Then it exits 3 and names the unreviewed rows

  Scenario: Schema error
    Given a dataset with a schema error
    When main is called
    Then it returns 2

  Scenario: Langfuse keys are required
    Given env without Langfuse keys
    When main is called on reviewed datasets
    Then it returns 2 with "evals: error: eval runs must be traced: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"

  Scenario: Pre-flight budget abort
    Given prices that make the estimate exceed --budget-usd 0.01
    When main is called
    Then it returns 4
    And the fake LLM receives no request

  Scenario Outline: Budget argument bounds
    When main is called with --budget-usd <value>
    Then it returns 2

    Examples:
      | value |
      | 0     |
      | -1    |
      | 51    |
      | nan   |

  Scenario: Completed run writes reports
    Given one reviewed case per dataset and fake services
    When main is called
    Then it returns 0
    And the JSON and Markdown reports exist with status "completed"
    And stdout contains the documented lines in order
    And services.aclose was awaited

  Scenario: In-flight abort writes a partial report
    Given costs that trip the in-flight backstop
    When main is called
    Then it returns 4 and the written report has status "aborted_budget"

  Scenario: End to end with mock OpenRouter
    Given an index in tmp_path built with FakeEmbedder
    And a mock HTTP transport answering GET /models, /embeddings and /chat/completions (router, answer citing [[moves/hack-and-slash]], judge JSON)
    And a memory span exporter
    When main runs one reviewed answerable rules case via default_services_factory with those seams
    Then it returns 0
    And the judge request used model "m-judge" and the other requests used the config models
    And exported spans have trace name "eval_turn", session.id equal to the run id, metadata eval_config "test" and model_judge "m-judge", and tag "config:test"
    And an "eval_case" event and a "judge_key_facts" generation are present

  Scenario: evals imports no vendor SDK
    When every .py file under evals/ (tests included) is AST-scanned
    Then none imports openai, langfuse, httpx2, numpy or opentelemetry
    And imports from backend.tests.adapter_helpers are allowed
    And evals/run.py and evals/tests/test_cli.py were among the scanned files
```

## Technical Notes

- **R-LABEL (critical):** per **D1** and **Validation Rules → check order in `main`**, `ensure_reviewed` runs on every selected dataset at stage 5, after arguments, config, `known_ids_from` and dataset schema, and **before** env, services and pre-flight budget. Stages 1–6 make no network call and build nothing. `UnreviewedRowsError` maps to exit `3`. No `--allow-unreviewed` or similar flag. `run_datasets` (story 004) keeps its own first-statement check; do not remove it.
- **Architecture / Design Overview** (steps 1–9), **D7**, **D10** (pre-flight), **D12**, **D18**, **D19** (`git rev-parse HEAD`, 5 s timeout, `null` on failure).
- **Configuration → CLI** (flags, stdout lines), **Constants** for `evals/run.py`.
- **Data Model → `evals/run.py`** (`EvalPaths`, `EvalServices`, `ServicesFactory`, `default_services_factory`, `main`) and the paragraph after it (seams imported from `backend/composition.py`, `build_runtime`/`build_eval_support` wiring, `aclose` order).
- **Tracing →** `main`'s `TraceOptions` metadata keys and tags.
- **Budget Guard →** pre-flight message and exit 4; in-flight stderr message.
- **Validation Rules →** CLI and Env rows.
- **Testing → Helpers:** add `fixture_paths` and `FAKE_ENV` to `evals/tests/helpers.py`.
- **Impact on Existing Code →** `evals/run.py`, `evals/tests/test_cli.py`, `evals/tests/test_layering.py`.

## Tests

- `evals/tests/test_cli.py`: `test_cli_refuses_unreviewed_row`, `test_cli_refuses_missing_reviewed_key`, `test_cli_single_unreviewed_row_blocks_all_datasets`, `test_cli_has_no_unreviewed_override`, `test_cli_schema_error_exit_2`, `test_cli_requires_langfuse_keys`, `test_cli_preflight_budget_abort`, `test_cli_budget_arg_bounds`, `test_cli_completed_run_writes_reports`, `test_cli_inflight_abort_writes_partial_report`, `test_cli_end_to_end_with_mock_openrouter`.
- `evals/tests/test_layering.py`: `test_evals_import_no_vendor_sdks`.

**Priority:** Critical
**Dependencies:** 009-evals-runner-and-first-reports-002-candidate-datasets-unreviewed.md, 009-evals-runner-and-first-reports-005-metrics-and-reports.md
