# 009-evals-runner-and-first-reports-004-collector-judge-budget-and-runner

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner measuring the assistant
**I want** a runner that executes reviewed cases end to end through the assistant, judges key facts, collects tokens and cost per trace, and stops at a budget backstop
**So that** every case produces a traceable, cost-bounded record, and unreviewed labels can never be run even by a programmatic caller

## Acceptance Criteria

```gherkin
Feature: Collector, judge, budget and runner core

  # R-LABEL, second enforcement point
  Scenario: run_datasets refuses unreviewed rows before any call
    Given a Dataset with one row whose reviewed is False
    When run_datasets is called directly (not via main)
    Then UnreviewedRowsError is raised
    And the fake LLM client received no request
    And the judge client received no request
    And the FakeTracer recorded nothing

  Scenario: Router case end to end
    Given a reviewed router case
    When run_datasets runs it
    Then the CaseRecord has the TurnResult intent
    And latency_ms comes from the injected clock
    And the first record in the case's trace is the "eval_case" event with case_id and dataset
    And the turn's session id equals the run id

  Scenario: Judge runs only for answerable rules_answer cases
    Given an answerable rules case answered with kind "rules_answer"
    And an answerable rules case whose retrieval is empty (kind "rules_not_found")
    And an unanswerable rules case
    When run_datasets runs them
    Then the judge is called only for the first case
    And the second case scores 0 with no judge call
    And the third case makes no judge call

  Scenario: Move cases use the normalised classification
    Given a move case where the classifier returns an unknown move id
    When run_datasets runs it
    Then the recorded classification move id is "no_move" and the reply is a clarification

  Scenario: Turns never roll
    When run_datasets runs any cases
    Then roll_requested is False in every TurnInput

  Scenario: In-flight backstop aborts
    Given actual costs above the per-case bound and a small budget
    When run_datasets runs
    Then before the next case spent + case_bound exceeds the budget
    And the outcome is aborted after the case that crossed it
    And later cases are not run

  Scenario: Cases run in file order
    Given several datasets and cases
    When run_datasets runs
    Then cases run sequentially in dataset order and file order

  Scenario: Judge request shape
    When judge_request is built for a question, answer and facts
    Then the user prompt follows the documented tag layout with facts numbered from 0
    And schema name is "key_fact_verdicts", temperature 0 and max_tokens 600

  Scenario: Valid judge output parses
    Given JSON whose facts cover each index 0..n-1 exactly once
    When parse_judge_output is called
    Then (present, evidence) tuples are returned by index

  Scenario Outline: Invalid judge output is rejected
    Given judge output that is <bad>
    When parse_judge_output is called
    Then ValueError is raised

    Examples:
      | bad                    |
      | not JSON               |
      | missing an index       |
      | a duplicate index      |
      | an out-of-range index  |
      | present: 1             |

  Scenario: Judge generation recorded in the case trace
    When judge_key_facts runs
    Then the FakeTracer receives a generation with node "judge_key_facts" and the case trace id

  Scenario: Judge PortError
    Given the judge client raises PortError
    When judge_key_facts runs
    Then JudgeError is raised and no generation is recorded

  Scenario: Invalid judge output is still traced and costed
    Given judge text "not json" with cost_usd 0.002
    When judge_key_facts runs
    Then JudgeError is raised
    And a "judge_key_facts" generation is recorded
    And generation_cost of it is (0.002, False)

  Scenario: Case bound formula
    Given prices 1e-6 prompt / 2e-6 completion and default GraphSettings
    Then case_bound matches the hand-computed value for a router case
    And for an answerable rules case including the judge bound
    And for an unanswerable rules case without the judge bound

  Scenario: Bound scales with retrieval_k
    When retrieval_k increases
    Then case_bound increases accordingly

  Scenario: Unknown cost uses the fallback
    Given a generation with cost_usd None
    When generation_cost is called
    Then it returns (UNKNOWN_CALL_COST_USD, True)
```

## Technical Notes

- **R-LABEL (critical):** per **D1** and **Data Model → `evals/runner.py`**, the **first statement** of `run_datasets` is `ensure_reviewed(d)` for every `d` in `datasets` (from story 001). It must raise `UnreviewedRowsError` before any tracer, assistant or judge call. There is no parameter or flag to bypass it. This is independent of, and in addition to, the check in `main` (story 006).
- **D3**, **D5**, **D9**, **D10** (in-flight backstop and `UNKNOWN_CALL_COST_USD`), **D11**.
- **Data Model → Python types:** `evals/collector.py` (`TraceRecords`, `CollectingTracer`), `evals/judge.py` (`FactVerdict`, `judge_schema`, `judge_request`, `parse_judge_output`, `judge_key_facts`, `JudgeError`), `evals/budget.py` (`call_cost`, `case_bound`, `estimate`, `generation_cost`), `evals/runner.py` (`CaseRecord`, `RunOutcome`, `run_datasets`).
- **Configuration → Constants** for `evals/budget.py` and `evals/judge.py`.
- **Key-Fact Judge** (request, prompt layout, rubric 1–7, schema, parsing rules, record-before-parse).
- **Budget Guard** (formula, in-flight backstop; `estimate` is used by the pre-flight check wired in story 006).
- **Tracing → "Per case, the runner"** steps 1–4.
- **Testing → Helpers:** add `fake_services` and the local `CostingLLMClient` to `evals/tests/helpers.py`. `fake_services` returns a `ServicesFactory` and builds `EvalServices`, whose types are defined in `evals/run.py` (**Data Model → `evals/run.py`**); if needed here, declare only those types (`EvalPaths`, `EvalServices`, `ServicesFactory`) in `evals/run.py` and leave `main` / `default_services_factory` to story 006.
- No metric computation or report writing in this story (stories 005–006).

## Tests

- `evals/tests/test_runner.py`: `test_run_datasets_refuses_unreviewed_before_any_call`, `test_router_case_end_to_end`, `test_rules_case_runs_judge_only_for_rules_answer`, `test_move_case_uses_normalised_classification`, `test_turns_never_roll`, `test_inflight_backstop_aborts`, `test_cases_run_in_file_order`.
- `evals/tests/test_judge.py`: `test_judge_request_shape`, `test_parse_judge_output_valid`, `test_parse_judge_output_invalid`, `test_judge_records_generation_in_case_trace`, `test_judge_port_error_becomes_judge_error`, `test_judge_invalid_output_still_recorded`.
- `evals/tests/test_budget.py`: `test_case_bound_formula`, `test_bound_scales_with_retrieval_k`, `test_generation_cost_unknown_uses_fallback`.

**Priority:** Critical
**Dependencies:** 009-evals-runner-and-first-reports-001-dataset-schema-rlabel-gate-and-config.md, 009-evals-runner-and-first-reports-003-backend-tracing-pricing-and-judge-seams.md
