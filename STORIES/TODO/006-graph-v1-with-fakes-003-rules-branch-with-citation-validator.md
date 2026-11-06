# 006-graph-v1-with-fakes-003-rules-branch-with-citation-validator

**Spec:** STORIES/SPECS/006-graph-v1-with-fakes.md

**As a** Dungeon World player asking a rules question
**I want** an answer grounded in retrieved rulebook sections, with citations that are guaranteed to point to those sections
**So that** I can trust the answer and follow its links, and I am told plainly when the rules do not cover my question

## Acceptance Criteria

```gherkin
Scenario: Rules question routed to retrieval
  Given the router returns "rules_question" and the retriever returns one chunk
  And the answer LLM cites that chunk
  When the turn runs
  Then the retriever is called once with (message, 6)
  And the reply kind is "rules_answer"

Scenario: Answer with valid citations
  Given chunks "moves/hack-and-slash" and "moves/defy-danger"
  And the answer "Deal damage [[moves/hack-and-slash]]."
  When the turn runs
  Then the reply kind is "rules_answer" with one Citation(section_id, title, "/rules/moves/hack-and-slash/")
  And retrieved_section_ids equals both ids

Scenario: Unretrieved citations are stripped and traced
  Given an answer citing one retrieved id and one unknown id
  When the turn runs
  Then the unknown marker is absent from the text
  And a "citations_stripped" event with ids "<unknown id>" and count 1 is traced

Scenario: No valid citation falls back to "not found" with closest sections
  Given 5 retrieved chunks and an answer citing only unknown ids, or no markers at all
  When the turn runs
  Then the reply kind is "rules_not_found" with text NOT_FOUND_TEXT
  And its citations are the first 3 chunks in retriever order
  And a "no_valid_citation" event is traced (for the unknown-ids case)

Scenario: Empty retrieval skips the answer LLM
  Given the retriever returns no chunks
  When the turn runs
  Then the reply kind is "rules_not_found" with no citations
  And only the router LLM request was made

Scenario: Answer prompt contains the retrieved sections
  When the answer node runs
  Then its request has role "answer", max_tokens 700 and no schema
  And its user prompt contains "[[<section_id>]] <title>" for each chunk

Scenario: Port failures end the turn with the error reply
  Given the retriever raises PortError("down") or the answer LLM raises PortError
  When the turn runs
  Then the reply kind is "error"
  And for the retriever case a "port_error" event with port "retriever" is traced

Scenario: check_citations is deterministic
  Given an answer text and a set of retrieved ids
  When check_citations runs
  Then valid markers are kept verbatim, invalid markers are removed with their preceding whitespace
  And valid_ids / invalid_ids are distinct ids in first-appearance order
  And single-bracket or whitespace-containing brackets are left untouched

Scenario: Rules path is fully traced
  Given the rules path
  When the turn runs
  Then tracer node names are ["router", "retrieve", "answer_with_citations", "citation_validator"]
  And two GenerationTraces are recorded (roles router, answer; models "fake-router"/"fake-answer"; tokens 10/5)
  And the router NodeTrace attributes equal {"intent": "rules_question", "confidence": 0.9}
```

## Technical Notes

Implements (per Suggested Story Breakdown item 3):
- Assumptions & Decisions → D12, D13.
- Data Model → `backend/graph/citations.py` (`CitationCheck`, `check_citations`).
- Graph Behaviour → *Wiring* (router `rules_question → retrieve`, conditionals after `retrieve` and `answer_with_citations`, `citation_validator → END`); *Rules branch* (`retrieve`, `answer_with_citations`, `citation_validator`, `check_citations` rules); *Tracing* → `retrieve` {`count`} and `citation_validator` {`valid`, `stripped`} attributes, `port_error` with `port: "retriever"`, `citations_stripped`, `no_valid_citation` events; *Prompts* → `RULES_SYSTEM` + `rules_user` row.
- User-Facing Copy → `NOT_FOUND_TEXT`.
- Files: `backend/graph/citations.py`, `backend/graph/rules_branch.py`, `backend/graph/prompts.py`, `backend/graph/replies.py`, `backend/graph/builder.py`, `backend/tests/test_graph_citations.py`, `backend/tests/test_graph_rules_branch.py`, `backend/tests/test_graph_router.py`, `backend/tests/test_graph_tracing.py`.

Independent of story 004 (move branch).

## Tests

- `test_graph_citations.py`: `test_all_citations_valid_kept`, `test_invalid_citation_stripped_with_preceding_space`, `test_duplicate_citations_deduplicated_in_order`, `test_no_markers_means_no_valid_ids`, `test_all_invalid`, `test_non_marker_brackets_untouched`.
- `test_graph_rules_branch.py`: `test_answer_with_valid_citations`, `test_invalid_citation_stripped_and_traced`, `test_no_valid_citation_returns_not_found_with_closest_sections`, `test_answer_without_citations_returns_not_found`, `test_empty_retrieval_skips_answer_llm`, `test_answer_prompt_contains_retrieved_sections`, `test_retriever_port_error_returns_error`, `test_answer_port_error_returns_error`.
- `test_graph_router.py`: `test_routes_rules_question_to_rules_branch`.
- `test_graph_tracing.py`: `test_every_executed_node_is_traced` (rules case), `test_generation_traced_per_llm_call`, `test_router_node_attributes`.

**Priority:** High
**Dependencies:** 006-graph-v1-with-fakes-002-graph-skeleton-router-out-of-scope-tracing.md
