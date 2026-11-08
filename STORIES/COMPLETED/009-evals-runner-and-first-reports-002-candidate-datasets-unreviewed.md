# 009-evals-runner-and-first-reports-002-candidate-datasets-unreviewed

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner (experienced GM)
**I want** draft candidate rows for the router, rules QA and move classification datasets, all marked unreviewed, plus a labelling guide
**So that** I can review and correct labels against the rules text before any metric is computed

## Acceptance Criteria

```gherkin
Feature: Candidate datasets, all unreviewed

  Scenario: No row is marked reviewed
    Given the three committed files under evals/datasets/
    When `grep -c '"reviewed": true' evals/datasets/*.jsonl` is run
    Then it reports 0 for every file
    And `grep -c '"reviewed": false'` equals each file's line count

  Scenario: Committed datasets are schema-valid
    Given data/normalized/ is present
    When router.jsonl, rules_qa.jsonl and move_classification.jsonl are loaded with known_ids_from(data/normalized)
    Then all three load without DatasetError
    And every row has a "reviewed" key with a JSON bool value

  Scenario: Committed-dataset tests skip only when data is absent
    Given data/normalized/sections.json is absent
    When test_committed_datasets.py runs
    Then its tests are skipped with reason "data/normalized not built yet"

  Scenario: Router coverage
    Given router.jsonl
    Then it has at least 40 rows
    And each of the three intents has at least 8 rows

  Scenario: Rules QA coverage
    Given rules_qa.jsonl
    Then it has at least 40 rows
    And at least 8 rows are unanswerable

  Scenario: Move classification coverage
    Given move_classification.jsonl
    Then it has at least 80 rows
    And every one of the 21 move ids is an expected_move_id at least once
    And each of the 8 basic moves has at least 3 rows
    And at least 15 rows expect "no_move"
    And at least 2 rows pair defy-danger and hack-and-slash (one expected, the other an acceptable alternative)
    And at least 2 rows pair spout-lore and discern-realities

  Scenario: Labelling guide exists
    Given evals/README.md
    Then it states the purpose, the three file shapes and R-LABEL in full
    And it lists the six-step owner review procedure
    And it contains the Dataset Drafting coverage checklist, how to run (make eval CONFIG=baseline), the meaning of exit codes 3 and 4, and that reports are committed by the owner
```

## Technical Notes

- **Rule R-LABEL** points 1, 2 and 4: **no file under `evals/datasets/` may contain `"reviewed": true`** after this story. Candidates are drafted from `data/normalized/moves.json` / `sections.json` (source text wins, handoff 12), never by running the assistant or any model named in `evals/configs/`.
- **Dataset Drafting (candidate rows)** — the full coverage table, including the non-test checklist items (≥ 5 mixed and ≥ 5 adversarial router cases; 1–5 atomic key facts from the cited section; question spread; alternatives only for genuine ambiguity) and the id scheme `router-NNN` / `rules-NNN` / `move-NNN`.
- **Data Model → Dataset files** (key order, encoding, LF, trailing newline). **D2**, **D17**.
- **Documentation → `evals/README.md`**.
- **Impact on Existing Code →** `evals/datasets/router.jsonl`, `rules_qa.jsonl`, `move_classification.jsonl`, `evals/README.md`, `evals/tests/test_committed_datasets.py`. `evals/datasets/.gitkeep` stays.
- Named verification step: the two `grep -c` checks from **Success Criteria** (scenario 1 above). This is deliberately not a permanent test.
- `test_committed_datasets.py` only reads `evals/datasets/`.

## Tests

- `evals/tests/test_committed_datasets.py`: `test_committed_datasets_are_schema_valid`, `test_router_coverage`, `test_rules_coverage`, `test_move_coverage`.

**Priority:** High
**Dependencies:** 009-evals-runner-and-first-reports-001-dataset-schema-rlabel-gate-and-config.md
