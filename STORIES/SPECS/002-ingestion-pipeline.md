# 002 - Ingestion pipeline

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 001 (toolchain and submodule must exist).
**Reference:** `HANDOFF_dw-companion.md`, sections 3 (MVP item 1), 5, 10 (milestone 2).

## Scope

Parse the Sagelt/Dungeon-World InDesign-flavored XML (`vendor/dungeon-world/`) into the
normalized, typed representation the rest of the project depends on.

- First task, before writing the parser: inspect the actual XML structure and write
  `docs/source-notes.md` describing what was found (presentational tags, inconsistent
  nesting, special characters — whatever is actually there, not assumed).
- Parser is tolerant and loud: unknown tags are logged and counted, never silently dropped;
  the build fails if the unknown-tag count exceeds a documented threshold.
- Output exactly the three files and shapes from section 5:
  - `sections.json`: `{ id, chapter, title, slug, parent_id, order, text_markdown }`
  - `moves.json`: `{ id, name, category: "basic"|"special"|"class", class: string|null, stat, trigger, outcomes: { strong_hit, weak_hit, miss }, body_markdown, section_id }`
  - `classes.json`: minimal, enough for site pages.
- Move extraction is the fragile part (outcome bands are prose, not fields). Validate with
  tests asserting known moves parse correctly: Hack and Slash, Defy Danger, Volley, Discern
  Realities, Last Breath. A small hand-maintained override file for moves that cannot be
  parsed cleanly is acceptable — document it in `docs/source-notes.md` if used.
- Snapshot tests on the normalized JSON output so future changes are visible in diffs.

## Out of scope

- Class moves beyond what `classes.json` minimally needs for site pages — they stay
  searchable through RAG later (spec 006/007), never part of the move classifier.
- Site generation from this data (spec 004).
- The retrieval index build (spec 007) — this spec only produces the normalized JSON, not
  embeddings or a vector store.

## Acceptance (from handoff milestone 2)

Done when all basic and special moves parse with trigger, stat, and three outcome bands,
and the unknown-tag count is reported (and gated per the threshold above).
