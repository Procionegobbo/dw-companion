# 010-model-tuning-round-001-candidate-config-and-comparison-core

**Spec:** STORIES/SPECS/010-model-tuning-round.md

> **Start condition (spec D2, binding):** do not start this story until spec 009's owner gate is complete: every spec 009 story is implemented, the owner has reviewed every row in `evals/datasets/*.jsonl` (`"reviewed": true`), and a first `evals/reports/<date>-baseline.json` with `status: "completed"` is committed. This applies even though this story makes no paid call and produces no number.

**As a** project owner preparing the model tuning round
**I want** a `classifier-mini` candidate config and a comparison core that loads spec 009 reports, refuses incomparable ones and extracts the headline metrics
**So that** any configuration comparison rests on validated, comparable reports and identically defined metrics

## Acceptance Criteria

```gherkin
Background:
  Given spec 009's owner gate is complete (all 009 stories built, every dataset row reviewed, first baseline report committed)

Scenario: Candidate config differs from baseline only in the classifier
  Given the committed configs evals/configs/baseline.toml and evals/configs/classifier-mini.toml
  When both are loaded with spec 009's load_config
  Then their models differ only in classifier, which is "openai/gpt-4.1-mini" in classifier-mini
  And their graph values are equal
  And their judges are equal
  And evals/configs/baseline.toml is unmodified

Scenario Outline: Invalid report is rejected
  Given a report file with <problem>
  When load_report reads it
  Then a ComparisonError is raised whose message starts with the prefix documented in Validation Rules for <problem>

  Examples:
    | problem                          |
    | missing file                     |
    | invalid JSON                     |
    | schema_version 2                 |
    | status "aborted_budget"          |
    | labels.all_rows_reviewed false   |
    | missing datasets                 |
    | cases[0].latency_ms a string     |

Scenario: Reports using different judge models are incomparable
  Given two valid reports whose config.models.judge values differ
  When check_comparable runs
  Then a ComparisonError reports that the judges differ and key-fact coverage is not comparable

Scenario: Dataset label hashes differ
  Given two valid reports sharing a dataset whose sha256 values differ
  When check_comparable runs
  Then a ComparisonError names the dataset and both 12-hex sha256 prefixes

Scenario: No dataset is shared
  Given a router-only report and a rules-only report
  When check_comparable runs
  Then a ComparisonError says no dataset is present in every report

Scenario: Headline rows come from report metrics
  Given comparable fixture reports
  When headline_rows runs over the shared datasets
  Then each row's values and Cases match the fixture metrics per the Comparison Output row table
  And no_move recall Cases is the count of reference cases with expected_move_id "no_move"
  And no_move precision Cases renders "—"

Scenario: Cost and latency are recomputed from cases
  Given comparable reports with some null cost_usd cases
  When headline_rows runs
  Then cost means exclude null cost_usd cases
  And cost per intent covers only the shared datasets
  And latency p50 and p95 equal spec 009's metrics.percentile over all shared cases
  And a cost row whose cases are all null renders "n/a"

Scenario: Recall label reflects retrieval_k
  Given reports with equal retrieval_k
  Then the recall row label is "Retrieval recall@<k>" using the reference's retrieval_k
  Given reports whose retrieval_k values differ
  Then the recall row label is "Retrieval recall@k (k differs, see Configurations)"

Scenario Outline: Values and deltas are formatted per unit
  When format_value / format_delta are applied to <input>
  Then the output is <expected>

  Examples:
    | input                                      | expected                              |
    | rate 0.875, delta +0.025                   | "87.5%", "+2.5 pp"                    |
    | usd reference 0.00085, value 0.00125       | "+$0.00040 (+47%)"                    |
    | negative usd delta                         | leading "-$" with negative percentage |
    | usd reference 0                            | no percentage                         |
    | ms value and delta                         | "<v> ms", signed "<d> ms"             |
    | None on either side                        | "n/a"                                 |

Scenario: Spec 009 tests stay untouched
  Then spec 009's tests pass unmodified
  And the only change in evals/tests/test_config.py is the added classifier-mini test
```

## Technical Notes

- **Configuration → `evals/configs/classifier-mini.toml`** (exact content given in the spec); D4, D5, D16 (`baseline.toml` not modified).
- **Configuration → Constants**: those used by this slice (`MIN_REPORTS`, `MAX_REPORTS`, `REPO_ROOT`; the rest may be added here or in later stories).
- **Data Model**: `ComparisonError`, `LoadedReport`, `load_report`, `assign_labels` (D13 labelling), `check_comparable`, `Unit`, `MetricRow`, `headline_rows`, `format_value`, `format_delta`. `case_flips`, `CaseFlips` and `config_diff` are in story 002.
- **Validation Rules**: all Report rows, the Comparability rows and the Metric values row. CLI rows belong to story 003.
- **Comparison Output → section 5 (`## Results`)**: the row table (sources and `Cases`), the recall-label rule and the formatting table — as data and formatting functions only; rendering the table is story 002.
- **Assumptions & Decisions**: D6, D7, D9, D13, D18 (imports limited to stdlib, `evals.datasets`, `evals.metrics`).
- Files: `evals/configs/classifier-mini.toml` (create), `evals/compare.py` (create), `evals/tests/test_compare.py` (create, including the `report(...)` fixture builder under the *Testing* fixture rule), `evals/tests/test_config.py` (additive).
- No-fabrication rule (Feature Description, D1) applies: fixtures only in `tmp_path`, obviously synthetic values.

## Tests

`evals/tests/test_compare.py`:
- `test_load_report_errors`
- `test_rejects_different_judge`
- `test_rejects_dataset_sha_mismatch`
- `test_rejects_no_shared_dataset`
- `test_headline_rows_values_and_cases`
- `test_cost_and_latency_recomputed_from_cases`
- `test_format_value_and_delta`
- `test_recall_label_uses_k_or_flags_difference`

`evals/tests/test_config.py` (additive):
- `test_classifier_mini_config_differs_from_baseline_only_in_classifier`

**Priority:** High
**Dependencies:** None within this spec (subject to the spec 009 owner-gate start condition above)
