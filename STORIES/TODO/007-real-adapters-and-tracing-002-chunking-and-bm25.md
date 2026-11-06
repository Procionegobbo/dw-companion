# 007-real-adapters-and-tracing-002-chunking-and-bm25

**Spec:** STORIES/SPECS/007-real-adapters-and-tracing.md

**As a** developer of the DW companion
**I want** the rulebook turned into section/move chunks and a keyword (BM25) scorer over them
**So that** retrieval works on semantic units that cite the right rules page and exact game terms rank well

## Acceptance Criteria

```gherkin
Scenario: Move sections are replaced by move chunks
  Given normalized sections and moves
  When build_chunks runs
  Then each move's section yields exactly one chunk of type "move", titled with the move name,
       whose text is the move's body_markdown stripped

Scenario: Excluded and empty sections
  Then no chunk has chapter "thanks"
  And a section whose text_markdown is empty yields no chunk

Scenario: Oversized sections split on block boundaries
  Given a section longer than MAX_CHUNK_CHARS
  Then it is split into consecutive parts with ids "<sid>#1".."<sid>#n" sharing section_id, title and anchor_url
  And every part is <= 6000 characters unless it is a single block
  And joining the parts with "\n\n" reproduces the normalised block sequence
  And a single 7,000-character block stays one whole part
  And a move longer than 6,000 characters is never split (parts == 1)

Scenario: Citation contract and index text
  Then every chunk's anchor_url equals "/rules/<section_id>/"
  And a child section's index_text is "<chapter title> > <title>\n\n<text>"
  And a chapter root section's index_text is "<title>\n\n<text>"

Scenario: Determinism and committed data
  When build_chunks runs twice on the same input
  Then chunks_to_json output is identical
  Given committed data/normalized exists
  Then it yields 21 move chunks, unique chunk_ids, no thanks chunk and no section chunk for a move's section
  Given committed data/normalized is absent
  Then that test skips with reason "data/normalized not built yet"

Scenario: BM25 tokenizer and scoring
  Then tokenize("Hack and Slash’s 10+ (STR)") == ["hack", "and", "slash", "s", "10", "str"]
  And the query "hack and slash" ranks the Hack and Slash document first
  And a term present in every document scores >= 0
  And a query with no overlap, or an empty query, scores 0 for every document
  And the same term frequency scores higher in a shorter document
```

## Technical Notes

- Assumptions & Decisions → D5 (in-house BM25 formula), D6 (tokenizer), D8 (chunking rules), D9 (`anchor_url`), D10 (index text).
- Configuration → Constants: `MAX_CHUNK_CHARS`, `EMBED_MAX_CHARS`, `EXCLUDED_CHAPTERS` (`chunking.py`); `BM25_K1`, `BM25_B` (`bm25.py`).
- Data Model → `IndexChunk`, `build_chunks`, `chunks_to_json`, `tokenize`, `BM25Index`; Index artifact → `chunks.json` key order (the format `chunks_to_json` produces); Chunk order and ids.
- Adapter Behaviour → Chunking; BM25.
- Validation Rules → all `IndexChunk` rows.
- Files: `backend/adapters/retrieval/__init__.py`, `backend/adapters/retrieval/chunking.py`, `backend/adapters/retrieval/bm25.py`, `backend/tests/adapter_helpers.py` (add `mini_normalized`, per the Testing → Helpers table), `backend/tests/test_adapters_chunking.py`, `backend/tests/test_adapters_bm25.py`.
- No new dependency in this story.

## Tests

`test_adapters_chunking.py`: `test_move_section_replaced_by_move_chunk`, `test_thanks_chapter_excluded`, `test_empty_sections_skipped`, `test_oversized_section_split_on_block_boundaries`, `test_single_huge_block_kept_whole`, `test_moves_never_split`, `test_anchor_url_matches_url_contract`, `test_index_text_header`, `test_build_chunks_deterministic`, `test_committed_data_chunks_valid`.

`test_adapters_bm25.py`: `test_tokenize`, `test_exact_term_ranks_first`, `test_idf_never_negative`, `test_no_overlap_scores_zero`, `test_empty_query_scores_zero`, `test_length_normalisation`.

**Priority:** High
**Dependencies:** 007-real-adapters-and-tracing-001-openrouter-llm-adapter-and-rulebook.md
