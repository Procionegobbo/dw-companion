# 006-graph-v1-with-fakes-004-move-branch-classify-clarify-explain

**Spec:** STORIES/SPECS/006-graph-v1-with-fakes.md

**As a** Dungeon World player describing what my character does
**I want** the assistant to tell me which basic or special move it triggers (or that none does), explain it with its outcomes quoted verbatim, and ask one clarifying question when unsure
**So that** I learn the right move and roll without the assistant guessing or inventing outcome text

## Acceptance Criteria

```gherkin
Scenario: Action routed to the classifier with every candidate move
  Given the router returns "action_description"
  When the turn runs
  Then the classifier is called and the retriever is not
  And the classifier request has role "classifier", temperature 0.0, max_tokens 400
  And its prompt has a line (id and trigger) for each basic/special move and its schema enum lists those ids plus "no_move"
  And class moves are absent from both prompt and schema enum

Scenario: Confident move is explained with verbatim outcomes
  Given the classifier returns "hack-and-slash" at 0.9
  When the turn runs
  Then the reply kind is "move" and its text equals the scripted explanation
  And move.outcomes is the Move's own outcomes object, move.url is "/moves/hack-and-slash/", roll is None

Scenario: Low confidence asks exactly one clarifying question
  Given the classifier returns "hack-and-slash" at 0.4 with alternatives ["defy-danger"]
  When the turn runs
  Then the reply kind is "clarification" with the exact template text from User-Facing Copy
  And no answer LLM request is made and a "clarification_requested" event is traced
  And at most three options are named

Scenario: Clarify threshold boundary
  Then confidence 0.6 yields "move" and 0.59 yields "clarification"

Scenario: "No move" is a first-class answer
  Given the classifier returns "no_move" at 0.9 with rationale "Walking into town triggers nothing."
  When the turn runs
  Then the reply is kind "no_move" with text "No move is triggered. Walking into town triggers nothing."
  And move is None and no answer request is made
  And "no_move" at 0.3 yields "clarification"

Scenario: Classifier output is normalised deterministically
  Given an unknown move_id "backstab" at 0.95
  Then the classification becomes move_id "no_move", confidence 0.0, the reply is "clarification", and "classifier_unknown_move" is traced
  Given alternatives with unknown ids or duplicates
  Then they are dropped keeping order and "classifier_alternatives_stripped" is traced
  Given a classifier stat that differs from the move's resolved roll_stat
  Then roll_stat follows the move per the resolve_roll_stat table and "classifier_stat_overridden" is traced

Scenario: Explanation request and roll phrase
  When explain runs for "hack-and-slash"
  Then the request has role "answer", max_tokens 300 and its user prompt contains the move name, trigger, message and "Roll: roll+STR"
  And roll_phrase never yields a bare None stat

Scenario: Failures end the turn with the error reply
  Given the classifier raises PortError, returns "{}", or the explanation raises PortError or is blank
  When the turn runs
  Then the reply kind is "error"
  And a classifier PortError makes no answer request, an explain PortError traces "port_error" with port "llm", and a blank explanation traces "llm_output_invalid"

Scenario: Action plus rules question prefers the move branch
  Given the router returns "action_description" for "I swing at the orc, does armor reduce damage?"
  Then the reply kind is "move" and the explain prompt contains the full message

Scenario: Low router confidence does not branch
  Given the router returns "action_description" at 0.42 and the classifier "hack-and-slash" at 0.9
  Then the reply kind is "move", router_confidence is 0.42 and intent is "action_description"

Scenario: Move paths are traced
  Then the clarify path traces ["router", "classify_move", "clarify"]
  And the no_move path traces ["router", "classify_move", "no_move"]
```

## Technical Notes

Implements (per Suggested Story Breakdown item 4):
- Assumptions & Decisions → D8, D9, D10, D11, D14, D15, D16, D22.
- Data Model → `backend/graph/llm_outputs.py` → `classifier_schema`, `parse_classifier_output`.
- Graph Behaviour → *Wiring* (router `action_description → classify_move`, `classify_move` conditional, `clarify → END`, `no_move → END`, `explain` conditional); *Move branch* (`classify_move` with normalisation steps 1–3, `resolve_roll_stat` table, `roll_phrase` table, `clarify`, `no_move`, `explain` including the `NOT_ROLLED_TEXT` append); *Tracing* → `classify_move` attributes and the `classifier_*` / `clarification_requested` events; *Prompts* → `CLASSIFIER_SYSTEM` + `classifier_user` and `EXPLAIN_SYSTEM` + `explain_user` rows; *JSON Schemas* → `classifier_schema(ids)`.
- User-Facing Copy → `NOT_ROLLED_TEXT`, `no_move_text`, `clarification_text`.
- Validation Rules → Classifier output, Explanation rows.
- `roll` and `outcome` nodes are not in this story: until story 005, `explain`'s conditional ends at `END` on success.
- Files: `backend/graph/move_branch.py`, `backend/graph/llm_outputs.py`, `backend/graph/prompts.py`, `backend/graph/replies.py`, `backend/graph/builder.py`, `backend/tests/test_graph_move_branch.py`, `backend/tests/test_graph_llm_outputs.py`, `backend/tests/test_graph_router.py`, `backend/tests/test_graph_tracing.py`.

Independent of story 003 (rules branch).

## Tests

- `test_graph_llm_outputs.py`: `test_parse_classifier_output_valid`, `test_parse_classifier_output_invalid`, `test_classifier_schema_enumerates_candidates`.
- `test_graph_move_branch.py`: `test_classifier_receives_all_candidate_moves`, `test_class_moves_excluded_from_candidates`, `test_confident_move_explained_with_verbatim_outcomes`, `test_low_confidence_asks_one_clarifying_question`, `test_clarification_threshold_boundary`, `test_clarification_text_option_counts`, `test_clarification_truncates_to_three_options`, `test_no_move_is_first_class`, `test_low_confidence_no_move_clarifies`, `test_unknown_move_id_forces_clarification`, `test_unknown_alternatives_stripped`, `test_roll_stat_resolution`, `test_explain_request_parameters`, `test_roll_phrase_cases`, `test_explain_port_error_returns_error`, `test_classifier_port_error_returns_error`, `test_empty_explanation_returns_error`, `test_classifier_invalid_output_returns_error`, `test_action_with_rules_question_prefers_move_branch`.
- `test_graph_router.py`: `test_routes_action_to_move_branch`, `test_low_router_confidence_does_not_branch`.
- `test_graph_tracing.py`: `test_every_executed_node_is_traced` (clarify and no_move cases).

**Priority:** High
**Dependencies:** 006-graph-v1-with-fakes-002-graph-skeleton-router-out-of-scope-tracing.md
