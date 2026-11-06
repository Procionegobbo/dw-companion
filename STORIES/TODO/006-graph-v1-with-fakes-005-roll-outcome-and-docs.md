# 006-graph-v1-with-fakes-005-roll-outcome-and-docs

**Spec:** STORIES/SPECS/006-graph-v1-with-fakes.md

**As a** Dungeon World player who asks the assistant to roll for me
**I want** the dice rolled by deterministic code and the result resolved against the move's own outcome bands (or reported per modifier when I give none)
**So that** the dice and outcomes are never invented by the LLM, and maintainers have an ADR and architecture doc describing the graph

## Acceptance Criteria

```gherkin
Scenario: Roll with a modifier resolves the outcome
  Given "hack-and-slash", roll_requested True, modifier 1 and dice (4, 5)
  When the turn runs
  Then move.roll.dice == (4, 5), move.outcome.band == "strong_hit"
  And move.outcome.text is the move's strong_hit text
  And the reply text ends with "Rolled 4 + 5 + 1 = 10: 10+."

Scenario: Negative modifier and null miss
  Given dice (3, 3) and modifier -1
  Then the text ends with "Rolled 3 + 3 - 1 = 5: 6-." and outcome.text is None

Scenario: Stated miss
  Given "last-breath", dice (1, 1), modifier 0
  Then outcome.text equals its miss string

Scenario: Rolled move without an ability stat
  Given "last-breath" at 0.9, roll_requested True, modifier 0, dice (4, 4)
  Then the explain prompt contains "Roll: roll 2d6 with no stat added"
  And the card has stat "NONE", roll_stat None, outcome band "weak_hit"
  And the text ends with "Rolled 4 + 4 + 0 = 8: 7-9."

Scenario: Roll without a modifier reports bands per modifier
  Given dice (3, 5) and no modifier
  Then outcome is None and bands_by_modifier covers -3..+3 as specified
  And the text ends with "Rolled 3 + 5 = 8. Add your modifier: -3 to -2: 6-; -1 to +1: 7-9; +2 to +3: 10+."

Scenario: Rolling is opt-in and only for rolled moves
  Given roll_requested False, or a non-rolled move, or a no_move answer, or a clarification
  Then the random source records no draws
  And a non-rolled move's text ends with "Make Camp isn't rolled, so there is nothing to roll."
  And a no_move text ends with " There is nothing to roll."

Scenario: Seeded rolls are reproducible
  Given two assistants with random.Random(42)
  Then they produce identical roll.dice

Scenario: Move-with-roll path is traced
  Then tracer node names are ["router", "classify_move", "explain", "roll", "outcome"]

Scenario: Documentation
  Then docs/decisions.md has the new ADR with the required content
  And docs/architecture.md has the diagram, one paragraph per node and the reply-kind table
```

## Technical Notes

Implements (per Suggested Story Breakdown item 5):
- Assumptions & Decisions → D6, D7, D14, D26.
- Graph Behaviour → *Wiring* (`explain` conditional to `roll` iff `roll_requested and move.is_rolled`, `roll → outcome`, `outcome → END`); *Move branch* → `roll`, `outcome`; *Tracing* → `roll` {`dice_total`} attribute.
- User-Facing Copy → `roll_text_with_modifier`, `roll_text_without_modifier`.
- Data Model → `MoveCard.roll`, `outcome`, `bands_by_modifier` fields; domain imports `roll`, `band_label`, `resolve_outcome` (no dice or band logic re-implemented).
- Documentation → ADR and `docs/architecture.md`; Impact on Existing Code → `docs/decisions.md` (append) and `docs/architecture.md` (replace stub line, keep title).
- Files: `backend/graph/move_branch.py`, `backend/graph/replies.py`, `backend/graph/builder.py`, `backend/tests/test_graph_roll.py`, `backend/tests/test_graph_move_branch.py`, `backend/tests/test_graph_tracing.py`, `docs/decisions.md`, `docs/architecture.md`.

## Tests

- `test_graph_roll.py`: `test_roll_with_modifier_resolves_outcome`, `test_roll_negative_modifier_text`, `test_roll_stated_miss`, `test_roll_without_modifier_reports_bands`, `test_no_roll_unless_requested`, `test_non_rolled_move_is_not_rolled`, `test_no_move_with_roll_requested`, `test_clarification_never_rolls`, `test_seeded_rng_reproducible`.
- `test_graph_move_branch.py`: `test_rolled_move_without_ability_stat_is_explained_and_rolled`.
- `test_graph_tracing.py`: `test_every_executed_node_is_traced` (move+roll case).

**Priority:** High
**Dependencies:** 006-graph-v1-with-fakes-004-move-branch-classify-clarify-explain.md
