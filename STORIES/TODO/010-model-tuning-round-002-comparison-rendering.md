# 010-model-tuning-round-002-comparison-rendering

**Spec:** STORIES/SPECS/010-model-tuning-round.md

> **Start condition (spec D2, binding):** do not start this story until spec 009's owner gate is complete: every spec 009 story is implemented, the owner has reviewed every row in `evals/datasets/*.jsonl` (`"reviewed": true`), and a first `evals/reports/<date>-baseline.json` with `status: "completed"` is committed.

**As a** project owner comparing eval runs
**I want** comparable reports rendered into one Markdown comparison with provenance, differing settings, a README-ready results table, per-case flips and notes
**So that** I can judge whether a delta comes from the configuration or from noise, and paste the table into the ADR and README

## Acceptance Criteria

```gherkin
Background:
  Given spec 009's owner gate is complete (all 009 stories built, every dataset row reviewed, first baseline report committed)

Scenario: Shared and skipped datasets drive the output
  Given a full report and a router + move_classification report
  When the datasets are checked and the comparison is rendered
  Then shared is (router, move_classification) and skipped is (rules_qa,)
  And Notes lists rules_qa as skipped
  And the results table has no rules rows

Scenario: Case flips for router and move classification
  Given reference and candidate reports with differing correct cases
  When the comparison is rendered
  Then cases are matched by id and ids missing from either report are ignored
  And ids keep file order
  And more than 20 ids render the first 20 followed by ", … and N more"
  And zero ids render "none"

Scenario: Configuration table lists only differing settings
  Given baseline and classifier-mini fixture reports
  When the comparison is rendered
  Then the Configurations table has exactly one row, models.classifier
  Given two reports with identical configs
  Then the Configurations section reads "No setting differs: these are repeated runs of the same configuration."
  And in both cases the judge line "Judge (identical in all reports): `<judge>`." follows

Scenario: Three reports get one delta column per candidate
  Given three comparable reports
  When the comparison is rendered
  Then each non-reference value column is followed by a "Δ <Lk>" column

Scenario: Results table is wrapped by markers
  When the comparison is rendered
  Then TABLE_START and TABLE_END each appear exactly once
  And every line between them starts with "|"

Scenario: Different commits are flagged
  Given reports whose git_commit values differ (including a null)
  Then the Reports section is followed by the different-commits note
  Given reports with equal git_commit values
  Then the note is absent

Scenario: Judge errors are noted
  Given a report with rules_qa.metrics.judge_errors > 0
  Then Notes contains "Judge errors (excluded from key-fact coverage): <L>: <n>, …"
```

## Technical Notes

- **Data Model**: `CaseFlips`, `case_flips`, `config_diff`, `render_comparison`.
- **Comparison Output**: all seven sections in order (title, generated line, `## Reports`, `## Configurations`, `## Results`, `## Changed cases`, `## Notes`), using story 001's `headline_rows`, `format_value`, `format_delta`.
- **Configuration → Constants**: `MAX_FLIP_IDS`, `TABLE_START`, `TABLE_END`.
- **Assumptions & Decisions**: D7 (skipped datasets in Notes), D8 (reference and Δ columns), D10 (flips, pp per case), D12 (markers).
- Files: `evals/compare.py` (extend), `evals/tests/test_compare.py` (extend).
- No-fabrication rule (D1, *Testing* fixture rule) applies; no file is written under `evals/reports/`.

## Tests

`evals/tests/test_compare.py`:
- `test_shared_and_skipped_datasets_in_order`
- `test_case_flips_router_and_move`
- `test_config_diff_lists_only_differing_settings`
- `test_three_reports_have_delta_column_per_candidate`
- `test_table_markers_appear_once_and_wrap_table`
- `test_different_commits_note`
- `test_judge_errors_note`

**Priority:** High
**Dependencies:** 010-model-tuning-round-001-candidate-config-and-comparison-core.md
