# 002-ingestion-pipeline-003-move-extraction-and-overrides

**Spec:** STORIES/SPECS/002-ingestion-pipeline.md

**As a** player using the companion's move cards and classifier (via later specs)
**I want** the 8 basic and 13 special moves extracted into `moves.json` with trigger, stat and verbatim outcome bands
**So that** moves can be quoted from structured source data rather than regenerated

## Acceptance Criteria

```gherkin
Feature: Move extraction and overrides

  Scenario: Move lists match the source
    Given the real pinned source
    When it is built
    Then moves.json holds 21 moves in Moves.xml document order
    And the basic ids are exactly hack-and-slash, volley, defy-danger, defend, spout-lore, discern-realities, parley, aid-or-interfere
    And the special ids are exactly last-breath, encumbrance, make-camp, take-watch, undertake-a-perilous-journey, level-up, end-of-session, carouse, supply, recover, recruit, outstanding-warrants, bolster
    And every move has class null and section_id "moves/<id>"

  Scenario Outline: Named moves parse exactly
    Given the real pinned source
    When it is built
    Then move "<id>" matches the spec's Expected results for id, category, stat, trigger and outcomes
    Examples:
      | id                |
      | hack-and-slash    |
      | defy-danger       |
      | volley            |
      | discern-realities |
      | last-breath       |

  Scenario: Every rolled move has trigger, stat and hit bands
    Given the 15 rolled moves
    Then each has a non-empty trigger, a non-null stat,
        and outcomes with non-empty strong_hit and weak_hit and a miss key

  Scenario: Miss is present only where the source states it
    Then the moves with a non-null miss are exactly last-breath, take-watch, carouse, recruit

  Scenario: Non-rolled moves have no outcomes and no stat
    Then encumbrance, make-camp, level-up, end-of-session, recover, bolster have outcomes null and stat null

  Scenario: Rolled move stats follow the source
    Then defend is CON, spout-lore INT, parley/supply/outstanding-warrants CHA, aid-or-interfere BOND,
        take-watch and undertake-a-perilous-journey WIS, carouse and recruit NONE

  Scenario: Band segmentation rules
    Then parley's strong_hit and weak_hit both start with "On a hit they ask you for something" and weak_hit ends with "right now."
    And outstanding-warrants' weak_hit ends with "- Someone important to you has been put in a bad spot as a result of your actions"
    And undertake-a-perilous-journey's strong_hit contains "On a 10+" three times
    And every move's body_markdown equals the text_markdown of its section

  Scenario: Invalid moves fail the build
    Given a synthetic Moves.xml with a rolled move that has no weak hit
    When the source is built
    Then an IngestionError is raised
    Given a synthetic Moves.xml with a move under an h1 other than "Basic Moves" / "Special Moves"
    When the source is built
    Then an IngestionError is raised

  Scenario: Overrides are exactly the documented six and are verbatim
    Then MOVE_OVERRIDES has exactly the six entries in the spec's Move Overrides table
    And each targets an existing move
    And each band string is a verbatim substring of that move's body_markdown
    And each overridden field differs from the result of build(SOURCE_DIR, overrides={})

  Scenario: Invalid overrides fail the build
    Given an overrides mapping with band text not in the move body, or an unknown move id, or a value equal to the automatic result
    When the source is built
    Then an IngestionError is raised

  Scenario: Regenerated output
    When `uv run python -m ingestion` runs
    Then moves.json is regenerated and committed
    And sections.json is unchanged
    And stdout reports "move overrides applied: 6"
```

## Technical Notes

Implements from the spec:

- **Python Modules & Interfaces → Move extraction (`moves.py`)**, steps 1–7; D6 (only the 21 `Moves.xml` moves; `class` always null), D7 (nullable `miss`), D8 (non-rolled moves), D9 (`stat` vocabulary), D10 (verbatim outcome strings, "On a hit" prefixes both hit bands).
- **Data Model → `moves.json`** table and `Move`/`Outcomes` `to_dict()` (Python `class_` → JSON `class`).
- **Python Modules & Interfaces → Public signatures** for `ingestion/overrides.py` (`MoveOverride`, `MOVE_OVERRIDES`) and the `overrides` parameter of `build()`; **Move Overrides** table (exact six entries); D11. `BuildResult.overrides_applied` reflects the applied entries.
- **Expected results for the named moves (test contract)**, full move lists and expected stats.
- **Validation Rules** rows: Move, Override.
- **Documentation → `docs/source-notes.md`** sections 6 (*Moves*) and 7 (*Move overrides*); **Documentation → `docs/decisions.md`** ADR-008 (must state the discrepancy with handoff milestone 2 and that the source wins).
- Per *Suggested Story Breakdown* item 3: regenerate and commit `moves.json`; `sections.json` must not change. Per item 2, this story updates the interim count assertion in `test_cli_writes_three_files_and_reports_counts` to reflect the moves now produced; story 004 sets the final form.

Files: `ingestion/moves.py`, `ingestion/overrides.py`, `ingestion/pipeline.py`, `ingestion/tests/test_moves.py`, `ingestion/tests/test_overrides.py`, `ingestion/tests/test_pipeline.py` (assertion update only), `data/normalized/moves.json`, `docs/source-notes.md`, `docs/decisions.md`.

## Tests

`ingestion/tests/test_moves.py` (all):
- `test_move_ids_match_source_lists`
- `test_named_move_parses_correctly`
- `test_every_rolled_move_has_trigger_stat_and_hit_bands`
- `test_miss_present_only_where_source_states_it`
- `test_unrolled_moves_have_no_outcomes_and_no_stat`
- `test_rolled_move_stats`
- `test_on_a_hit_prefixes_both_hit_bands`
- `test_list_after_band_attaches_to_that_band`
- `test_repeated_band_segments_are_joined`
- `test_move_body_equals_its_section_text`
- `test_rolled_move_without_weak_hit_fails_build`
- `test_move_under_unexpected_h1_fails_build`

`ingestion/tests/test_overrides.py` (all):
- `test_override_set_is_exactly_the_documented_six`
- `test_every_override_targets_an_existing_move`
- `test_override_bands_are_verbatim_substrings_of_move_body`
- `test_every_override_changes_the_automatic_result`
- `test_override_with_non_source_text_fails_build`
- `test_override_for_unknown_move_fails_build`
- `test_override_equal_to_automatic_value_fails_build`

**Priority:** Critical
**Dependencies:** 002-ingestion-pipeline-002-sections-pipeline-and-cli-unknown-gate.md
