# 002-ingestion-pipeline-004-classes-and-close-out

**Spec:** STORIES/SPECS/002-ingestion-pipeline.md

**As a** developer of the dw-companion site (spec 004)
**I want** a minimal `classes.json` for the 8 core classes, and the ingestion design recorded as an ADR
**So that** class pages can render a stat block from source data and the pipeline's design choices are documented

## Acceptance Criteria

```gherkin
Feature: Class extraction and close-out

  Scenario: The eight core classes in order
    Given the real pinned source
    When it is built
    Then classes.json holds bard, cleric, druid, fighter, paladin, ranger, thief, wizard in that order with order 0–7

  Scenario Outline: Class stats match the source
    Given the real pinned source
    When it is built
    Then class "<id>" has max_hp_base <hp>, base_damage "<dmg>", load_base <load>
    And its name is the capitalised class name without "The"
    Examples:
      | id      | hp | dmg | load |
      | bard    | 6  | d6  | 9    |
      | cleric  | 8  | d6  | 10   |
      | druid   | 6  | d6  | 6    |
      | fighter | 10 | d10 | 12   |
      | paladin | 10 | d10 | 12   |
      | ranger  | 8  | d8  | 11   |
      | thief   | 6  | d8  | 9    |
      | wizard  | 4  | d4  | 7    |

  Scenario: Class section ids resolve
    Then every class section_id equals its id and refers to an existing section

  Scenario: Missing stat line fails the build
    Given a synthetic Fighter.xml without the "Your load is N+Str" line
    When the source is built
    Then an IngestionError is raised naming the class and the field

  Scenario: Final CLI report
    When main(["--out", <dir>]) runs on the real source
    Then stdout contains "21 moves (15 rolled), 8 classes"

  Scenario: ADR-007 recorded
    When I open docs/decisions.md
    Then it contains ADR-007 "Ingestion: stdlib parser, chapter manifest, IDs, committed output as snapshot" in the same format as ADR-001…006
```

## Technical Notes

Implements from the spec:

- **Python Modules & Interfaces → Class extraction (`classes.py`)**; D15.
- **Data Model → `classes.json`** table and `GameClass.to_dict()`; **Chapter Manifest** → `CLASS_CHAPTER_IDS`; **Source Facts** → *Class stat lines*.
- **Python Modules & Interfaces → Public signatures** note: class extraction runs only for `CLASS_CHAPTER_IDS` present in `chapters`.
- **Validation Rules** row: Class.
- **Documentation → `docs/decisions.md`** ADR-007 (content from D2, D3, D4, D5, D12, D13, D14).
- Per *Suggested Story Breakdown* item 4: regenerate and commit `classes.json`, and update `test_cli_writes_three_files_and_reports_counts` (owned by story 002) to its final assertion `21 moves (15 rolled), 8 classes`.

Files: `ingestion/classes.py`, `ingestion/pipeline.py`, `ingestion/tests/test_classes.py`, `ingestion/tests/test_pipeline.py` (assertion update only), `data/normalized/classes.json`, `docs/decisions.md`.

## Tests

`ingestion/tests/test_classes.py` (all):
- `test_classes_are_the_eight_core_classes_in_order`
- `test_class_stats_match_source`
- `test_class_section_ids_resolve`
- `test_missing_class_stat_line_fails_build`

Plus the final-form assertion of `test_cli_writes_three_files_and_reports_counts` (test defined in story 002).

**Priority:** High
**Dependencies:** 002-ingestion-pipeline-002-sections-pipeline-and-cli-unknown-gate.md, 002-ingestion-pipeline-003-move-extraction-and-overrides.md (only for the final `21 moves (15 rolled)` report assertion)
