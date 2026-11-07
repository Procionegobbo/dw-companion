# 005-domain-and-dice-002-rulebook-types-and-parsers

**Spec:** STORIES/SPECS/005-domain-and-dice.md

**As a** backend developer building the rulebook repository (specs 006/007)
**I want** immutable, validated `Section`, `Move` and `Outcomes` types with pure parsers for the spec 002 JSON shapes
**So that** an invalid rulebook object cannot exist and drift in the ingestion output fails loudly

## Acceptance Criteria

```gherkin
Feature: Rulebook types and parsers

  Scenario: Named moves parse
    Given the five spec 002 move fixtures (Hack and Slash, Defy Danger, Volley, Discern Realities, Last Breath)
    When move_from_dict is called on each
    Then every field equals the fixture, with JSON "class" mapped to class_
    And outcomes is an Outcomes

  Scenario: Miss text may be absent
    Then last-breath has a miss string and hack-and-slash has miss None

  Scenario: Extended stat vocabulary
    Then moves with stat "VARIES", "NONE" and "BOND" all construct

  Scenario: Non-rolled move
    Given the make-camp fixture
    Then stat is None, outcomes is None and is_rolled is False
    And a rolled move such as hack-and-slash has is_rolled True

  Scenario: Outcomes text per band
    Then Outcomes.text_for returns the strong_hit, weak_hit and miss text for each band

  Scenario: Move invariants
    Given a move with stat set but outcomes None, or stat None but outcomes set
    Then ValueError is raised
    Given category "class" with class_ None, or category "basic" with a class_
    Then ValueError is raised
    But category "class" with class_ "fighter" succeeds

  Scenario: Invalid move values
    Given a fixture modified with a bad id, empty name, blank trigger, unknown stat, unknown category, empty strong_hit, empty-string miss, or bad section_id
    When move_from_dict is called
    Then ValueError is raised whose message contains the field name

  Scenario: Parser key and type checks
    Given a move or section dict missing a key or with an extra key
    Then ValueError naming the key is raised
    Given a move dict with stat 1, outcomes "x", or outcomes missing "miss"
    Then ValueError is raised

  Scenario: Sections parse and hierarchy is enforced
    Given the chapter and child section fixtures
    Then they construct with every field equal to the input
    But a chapter section with a parent, a child with parent_id None, a child whose id is not chapter/slug, or a chapter section whose slug differs from its id raises ValueError
    And order -1 or True raises ValueError, while empty text_markdown is accepted

  Scenario: Vocabularies
    Then STATS has the 9 values in declaration order, ABILITY_STATS the 6, BANDS the 3

  Scenario: Committed JSON is compatible
    Given data/normalized/moves.json and sections.json exist
    Then every element parses and the five named moves are present
    And every move's section_id is among the parsed section ids
    Given the files do not exist
    Then the tests skip with "spec 002 output not present"
```

## Technical Notes

- Data Model → `backend/domain/rulebook.py` block: `Stat`, `AbilityStat`, `Category`, `STATS`, `ABILITY_STATS`, `Outcomes` (`text_for`), `Move` (`is_rolled`), `Section`, `move_from_dict`, `section_from_dict`; and the JSON ↔ type mapping paragraph (`class` ↔ `class_`).
- Python Module Behaviour → `rulebook.py` paragraph (parser check order, `TypeGuard` helpers, error message naming the move id or `'?'`).
- Validation Rules → `SLUG` / `SECTION_ID` patterns and all `Outcomes`, `Move`, `Section`, and `move_from_dict` / `section_from_dict` rows.
- Assumptions & Decisions → D1, D2, D3, D4, D5, D10, D11, D12.
- Testing → fixture dicts (five named moves, make-camp, section fixtures) added to `backend/tests/domain_helpers.py`.
- Files: create `backend/domain/rulebook.py`, `backend/tests/test_domain_rulebook.py`; modify `backend/tests/domain_helpers.py`. `rulebook.py` imports `Band` from `dice.py`.

## Tests

`test_domain_rulebook.py` (all tests listed in the spec):
- `test_named_moves_parse`
- `test_last_breath_states_miss`
- `test_hack_and_slash_miss_is_none`
- `test_extended_stats_parse`
- `test_non_rolled_move_parses`
- `test_rolled_move_is_rolled`
- `test_outcomes_text_for_each_band`
- `test_stat_outcomes_consistency_enforced`
- `test_class_field_consistency_enforced`
- `test_invalid_move_values_rejected`
- `test_move_from_dict_rejects_missing_and_extra_keys`
- `test_move_from_dict_rejects_wrong_types`
- `test_sections_parse`
- `test_section_hierarchy_enforced`
- `test_section_order_rules`
- `test_section_from_dict_rejects_missing_and_extra_keys`
- `test_vocabularies`
- `test_committed_moves_json_parses`
- `test_committed_sections_json_parses`

**Priority:** High
**Dependencies:** 005-domain-and-dice-001-dice-resolution.md
