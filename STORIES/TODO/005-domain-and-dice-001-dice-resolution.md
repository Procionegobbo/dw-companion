# 005-domain-and-dice-001-dice-resolution

**Spec:** STORIES/SPECS/005-domain-and-dice.md

**As a** backend developer building the graph's `roll` tool (spec 006)
**I want** a pure, deterministic `2d6 + modifier` dice primitive that maps totals to the Dungeon World bands `10+ | 7-9 | 6-`
**So that** dice values always come from tested domain code with injected randomness, never from the LLM

## Acceptance Criteria

```gherkin
Feature: Dice resolution

  Scenario: Totals map to bands
    Given any int total
    When band_for_total is called
    Then a total >= 10 returns "strong_hit"
    And a total from 7 to 9 returns "weak_hit"
    And a total <= 6 returns "miss"

  Scenario: Band display labels
    When band_label is called for "strong_hit", "weak_hit", "miss"
    Then it returns "10+", "7-9", "6-" respectively (ASCII hyphen)

  Scenario: Rolling draws two d6 in order from the injected source
    Given a RandomSource scripted to return 3 then 5
    When roll(rng) is called
    Then the Roll's dice are (3, 5)
    And the source was called exactly twice with (1, 6)

  Scenario: Roll with a modifier has a total and band
    Given dice (4, 5) and modifier +1
    When the Roll is built
    Then total is 10 and band is "strong_hit"

  Scenario: Roll without a modifier
    Given dice (3, 5) and no modifier
    Then modifier, total and band are None and dice_total is 8
    And band_with(m) reports the band for any valid modifier m

  Scenario: Modifier bounds
    Given a modifier of -10 or +10
    Then roll, Roll and band_with accept it
    But a modifier of -11, +11 or a bool raises ValueError
    And roll validates the modifier before drawing, consuming no randomness

  Scenario: Invalid dice rejected
    Given a source returning a value outside 1-6, or a Roll with other than two dice
    Then ValueError is raised

  Scenario: Seeded randomness is reproducible
    Given two random.Random instances with the same seed
    Then they produce identical sequences of roll results
    And random.Random satisfies RandomSource structurally

  Scenario: Roll is immutable
    When a Roll field is assigned
    Then dataclasses.FrozenInstanceError is raised

  Scenario: Domain imports stay pure
    Given every backend/domain/*.py file
    Then each import is in the D13 allow-list
    And dice.py is among the scanned files
```

## Technical Notes

- Data Model → `backend/domain/dice.py` block: `Band`, `BANDS`, `MIN_MODIFIER`/`MAX_MODIFIER`, `RandomSource`, `band_for_total`, `band_label`, `Roll` (`dice_total`, `total`, `band`, `band_with`), `roll`.
- Python Module Behaviour → `dice.py` paragraph.
- Validation Rules → rows `roll` / `Roll` / `band_with` (`modifier`), `Roll` (`dice`), `band_for_total` (`total`).
- Assumptions & Decisions → D6, D7, D8, D9, D11, D13, D15, D17.
- Testing → `ScriptedRandom` in `backend/tests/domain_helpers.py` (only `ScriptedRandom` in this story; fixture dicts come in story 002).
- Files: create `backend/domain/dice.py`, `backend/tests/domain_helpers.py`, `backend/tests/test_domain_dice.py`, `backend/tests/test_domain_purity.py`. `backend/domain/__init__.py` stays empty.

## Tests

`test_domain_dice.py` (all tests listed in the spec):
- `test_band_boundaries`
- `test_band_for_every_reachable_total`
- `test_band_for_extreme_totals`
- `test_band_label`
- `test_roll_uses_two_d6_draws_in_order`
- `test_roll_with_modifier_totals_and_bands`
- `test_roll_without_modifier_has_no_total_or_band`
- `test_band_with_reports_band_per_modifier`
- `test_roll_band_matches_band_for_total_exhaustively`
- `test_modifier_out_of_range_rejected`
- `test_modifier_bounds_accepted`
- `test_bool_modifier_rejected`
- `test_die_out_of_range_rejected`
- `test_seeded_rolls_are_reproducible`
- `test_seeded_rolls_cover_all_faces`
- `test_random_random_works_as_random_source`
- `test_roll_is_immutable`

`test_domain_purity.py`:
- `test_domain_imports_are_pure`

**Priority:** Critical
**Dependencies:** None (requires spec 001 to have landed)
