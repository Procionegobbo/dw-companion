# 010-model-tuning-round-003-compare-cli-makefile-and-docs

**Spec:** STORIES/SPECS/010-model-tuning-round.md

> **Start condition (spec D2, binding):** do not start this story until spec 009's owner gate is complete: every spec 009 story is implemented, the owner has reviewed every row in `evals/datasets/*.jsonl` (`"reviewed": true`), and a first `evals/reports/<date>-baseline.json` with `status: "completed"` is committed.

**As a** project owner running the tuning round
**I want** a `make compare` command that writes the comparison file, plus a documented procedure, decision guidance and ADR template
**So that** I can run the round, choose a configuration and record it with traceable evidence, without the tooling ever inventing numbers

## Acceptance Criteria

```gherkin
Background:
  Given spec 009's owner gate is complete (all 009 stories built, every dataset row reviewed, first baseline report committed)

Scenario Outline: Report count out of bounds
  When compare.main runs with <n> report paths
  Then it exits 2
  And no comparison file is written

  Examples:
    | n |
    | 1 |
    | 5 |

Scenario: Comparison is written and suffixed on collision
  Given two comparable reports labelled a and b and a fixed now
  When compare.main runs twice
  Then the first run writes <date>-a-vs-b.md and the second writes <date>-a-vs-b-2.md
  And stdout is "compare: wrote <path>"
  And each run exits 0

Scenario: Duplicate config names get run-id suffixes
  Given two reports with the same config name
  When compare.main runs
  Then both labels become "<name>-<first 6 hex of run_id>"
  And those labels are used in the file name

Scenario: Error writes nothing
  Given an incomparable pair of reports
  When compare.main runs
  Then it exits 2
  And stderr starts with "compare: error: "
  And comparisons_dir does not exist

Scenario: End-to-end on real runner reports
  Given spec 009's evals.run.main run once per config (spec 009's fixture config from fixture_paths and a second configs/test-b.toml differing only in classifier "m-classifier-b") with spec 009's fakes on one reviewed case per dataset in tmp_path
  When compare.main runs on the two JSON reports
  Then it exits 0
  And the output has every result row, a models.classifier configuration row and a Changed cases section for router and move

Scenario: Makefile target
  When "make -n compare REPORTS=\"a.json b.json\"" runs
  Then it prints "uv run python -m evals.compare a.json b.json"
  And "make -n eval" prints the same command as before this spec

Scenario: Tuning-round documentation
  Then evals/README.md contains a "## Tuning round" section with the Owner Procedure, the D14 decision guidance and the ADR template
  And README.md's "### Running evals" gains one sentence pointing to make compare and evals/README.md

Scenario: Stories produce no results (named verification step)
  Then docs/decisions.md contains no tuning-round ADR
  And evals/reports/ contains no file added by this spec's stories
  And neither README.md nor evals/README.md contains an eval metric value
```

## Technical Notes

- **Data Model**: `comparison_path` (D11 suffixing), `main` (with `comparisons_dir` and `now` injection; `if __name__ == "__main__"` entry).
- **Configuration → CLI** (stdout/stderr text, exit codes), **Configuration → `Makefile`** (`compare` target with its own `.PHONY`; `eval` target and variables untouched), **Configuration → Constants** `DEFAULT_COMPARISONS_DIR`.
- **Validation Rules**: CLI rows; the check order in `main`; first failure stops the run and writes nothing; `now()` must be timezone-aware UTC.
- **Assumptions & Decisions**: D3, D11, D13 (labels in the file name), D14 and D15 (content for `evals/README.md`), D17 (no tooling ADR).
- **Owner Procedure**: reproduced in `evals/README.md` under `## Tuning round`, with the D14 guidance, the ADR template verbatim, and the note that the stories did not produce a comparison. The procedure itself is NOT performed by this story.
- **Impact on Existing Code**: `Makefile`, `evals/README.md`, `README.md` rows (all additive); `evals/reports/comparisons/` is not created by the story and gets no `.gitkeep`; `docs/decisions.md` unchanged.
- Files: `evals/compare.py` (extend), `evals/tests/test_compare.py` (extend), `Makefile`, `evals/README.md`, `README.md`.
- No-fabrication rule (D1): no eval number in any committed file.

## Tests

`evals/tests/test_compare.py`:
- `test_duplicate_config_names_get_run_id_suffix`
- `test_cli_report_count_bounds`
- `test_cli_writes_comparison_and_suffixes_on_collision`
- `test_cli_error_writes_nothing`
- `test_compare_end_to_end_on_runner_reports`

Manual: `make -n compare REPORTS="a.json b.json"` and `make -n eval` checks above.

**Priority:** High
**Dependencies:** 010-model-tuning-round-001-candidate-config-and-comparison-core.md, 010-model-tuning-round-002-comparison-rendering.md
