# 009-evals-runner-and-first-reports-005-metrics-and-reports

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner comparing configurations
**I want** fixed, reproducible metric definitions and a JSON plus Markdown report built from run records
**So that** every run yields comparable, auditable numbers with provenance

## Acceptance Criteria

```gherkin
Feature: Metrics and reports

  Scenario: Rate and percentile edge cases
    Then rate(1, 0) is None
    And percentile([], 50) is None
    And percentile([5], 95) == 5
    And percentile([1, 2, 3, 4], 50) == 2.5
    And percentile([1..20], 95) == 19.05

  Scenario: Router accuracy and confusion matrix
    Given 4 router records, one with intent None
    Then accuracy is 0.75
    And the confusion matrix has an "error" column and omits zero cells

  Scenario: Recall at k
    Then recall_at_k({a, b}, [b, c]) == 0.5
    And recall_at_k with empty retrieval == 0

  Scenario: Citation validity
    Given one answer with 2 valid and 1 stripped citations
    And one answer with 0 valid and 0 stripped
    And one rules_not_found after no_valid_citation with 0 valid and 2 stripped
    Then citation_validity_rate is 2/5
    And answers_without_citations == 1

  Scenario: Refusal rate and misrouted
    Given rules records including unanswerable cases and a misrouted case
    Then correct_refusal_rate counts unanswerable cases with kind "rules_not_found"
    And misrouted counts cases with intent != "rules_question"

  Scenario: Key-fact coverage
    Given answerable cases with judged verdicts, a judge_error case and a non-rules_answer reply
    Then key_fact_coverage excludes the judge_error case
    And scores the non-rules_answer case 0.0
    And judge_errors counts the error

  Scenario: Move accuracy counts alternatives
    Given a move case predicted as one of its acceptable_alternatives
    Then it counts as correct

  Scenario: Not-routed move case
    Given a move case without classification
    Then predicted is "(not routed)", it is incorrect, and it appears in the confusion matrix

  Scenario: no_move precision and recall
    Then no_move_precision and no_move_recall follow the definitions
    And each is null when its denominator is zero

  Scenario: Clarification rate
    Then clarification_rate = rate(kind == "clarification", n)

  Scenario: System metrics per intent
    Given records across intents including "error", with judge generations and some unknown-cost calls
    Then system has "all" plus each present intent
    And token and cost means exclude judge generations
    And cost_usd_mean only averages cases whose every turn generation has cost_usd, null if none
    And cost_unknown_calls is counted

  Scenario: Report shape and key order
    When build_report is called
    Then top-level keys appear in the documented order with schema_version 1
    And labels.all_rows_reviewed is True
    And config and dataset SHA-256 hashes are present

  Scenario: Report paths suffix on collision
    Given an existing 2026-11-20-test.json in the reports dir
    When report_paths is called for 2026-11-20 and "test"
    Then both the JSON and Markdown paths get the "-2" suffix

  Scenario: Markdown summary
    When render_markdown is called on a report
    Then it has a heading per dataset
    And null values render as "n/a"
    And listed failures are capped at 20 followed by "… and N more"

  Scenario: Rounding
    Then rates and recall are rounded to 4 decimals, USD to 6, milliseconds and token means to 1
```

## Technical Notes

- **D4**, **D12**, **D19** (report records config hash, dataset hashes and row counts, `git_commit`; the `git rev-parse` call itself is made by `main` in story 006 and passed in).
- **Metrics** — every table and paragraph: Router, Rules QA, Move classification, System, Case detail.
- **Data Model → Python types:** `evals/metrics.py` (all functions, `JsonValue`) and `evals/report.py` (`build_report`, `render_markdown`, `report_paths`, `write_report`).
- **Data Model → Report JSON (`schema_version` 1)** — key order, rounding, `eval_overhead` only for `rules_qa`, `labels.all_rows_reviewed` always `true`.
- Consumes `CaseRecord` / `RunOutcome` from `evals/runner.py` (story 004). Metrics are pure.
- **Authorization & Security → Secrets:** no secret is written to reports.

## Tests

- `evals/tests/test_metrics.py`: `test_rate_and_percentile`, `test_router_accuracy_and_confusion`, `test_recall_at_k`, `test_rules_citation_validity`, `test_rules_refusal_rate_and_misrouted`, `test_key_fact_coverage_excludes_judge_errors_and_scores_non_answers_zero`, `test_move_accuracy_counts_alternatives`, `test_move_not_routed_is_incorrect_and_in_matrix`, `test_no_move_precision_recall`, `test_clarification_rate`, `test_system_metrics_per_intent_excludes_judge_and_unknown_cost`.
- `evals/tests/test_report.py`: `test_report_shape_and_key_order`, `test_report_paths_suffix_on_collision`, `test_markdown_contains_metrics_and_failures`, `test_rounding`.

**Priority:** High
**Dependencies:** 009-evals-runner-and-first-reports-004-collector-judge-budget-and-runner.md
