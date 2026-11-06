# 005-domain-and-dice-003-outcome-resolution-and-adr

**Spec:** STORIES/SPECS/005-domain-and-dice.md

**As a** player using the companion
**I want** a roll on a move to resolve to that move's verbatim band text
**So that** the outcome I am told comes from the rulebook, never written by the LLM

## Acceptance Criteria

```gherkin
Feature: Outcome resolution

  Scenario: Resolve each band
    Given hack-and-slash and a roll with modifier 0
    When dice are (5,5) then the Outcome band is "strong_hit" with the 10+ text
    When dice are (3,4) then the band is "weak_hit" with the 7-9 text
    When dice are (1,2) then the band is "miss" and text is None

  Scenario: Stated miss
    Given last-breath and dice (1,1) with modifier 0
    Then the band is "miss" and text equals its miss string

  Scenario: Text is verbatim
    When a strong hit is resolved
    Then outcome.text is the same object as move.outcomes.strong_hit

  Scenario: Modifier is required
    Given a Roll with modifier None
    When resolve_outcome is called
    Then ValueError containing "modifier is required" is raised

  Scenario: Non-rolled move rejected
    Given make-camp
    When resolve_outcome is called
    Then ValueError containing "not rolled" is raised

  Scenario: Outcome invariants
    Given an Outcome whose band differs from roll.band, or whose roll has no band, or with text ""
    Then ValueError is raised

  Scenario: Decision recorded
    Then docs/decisions.md has a new ADR "Domain layer — stdlib types, mirrored ingestion shapes, injected dice randomness"
    And it states the band rule (>=10 / 7-9 / <=6), the modifier range -10...+10, and that only backend.domain.dice.roll produces dice values
```

## Technical Notes

- Data Model → `backend/domain/outcome.py` block (`Outcome`, `resolve_outcome`) and the paragraph on `Outcome.text` / `Outcome.band`.
- Python Module Behaviour → `outcome.py` condition table and `Outcome.__post_init__` invariants.
- Validation Rules → `Outcome` row.
- Documentation → ADR content; Assumptions & Decisions → D16 (ADR number = next free number in `docs/decisions.md`, existing ADRs untouched), D5.
- Files: create `backend/domain/outcome.py`, `backend/tests/test_domain_outcome.py`; modify `docs/decisions.md` (additive). Uses fixtures and `ScriptedRandom` from `backend/tests/domain_helpers.py`.

## Tests

`test_domain_outcome.py` (all tests listed in the spec):
- `test_resolve_strong_weak_miss`
- `test_resolve_stated_miss`
- `test_resolve_requires_modifier`
- `test_resolve_rejects_non_rolled_move`
- `test_outcome_text_is_verbatim`
- `test_outcome_invariants`

**Priority:** High
**Dependencies:** 005-domain-and-dice-001-dice-resolution.md, 005-domain-and-dice-002-rulebook-types-and-parsers.md
