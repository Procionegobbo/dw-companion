# 002-ingestion-pipeline-002-sections-pipeline-and-cli-unknown-gate

**Spec:** STORIES/SPECS/002-ingestion-pipeline.md

**As a** maintainer of dw-companion
**I want** `uv run python -m ingestion` to split every chapter into citation-sized sections, fail loudly on unknown markup or a manifest mismatch, and write deterministic JSON
**So that** downstream specs get a stable, committed `sections.json` contract and any upstream change shows up as a failed build or a snapshot diff

## Acceptance Criteria

```gherkin
Feature: Sectioning, build pipeline and CLI

  Scenario: Chapter heading is consumed when it matches the manifest title
    Given a chapter whose first heading is an h1 equal (casefold) to its manifest title
    When the source is built
    Then that h1 produces no section
    And the chapter section has id = chapter id, title = manifest title, parent_id = null

  Scenario: Non-matching first h1 becomes a child section
    Given a chapter whose first h1 differs from its manifest title (as in Moves.xml)
    When the source is built
    Then that h1 becomes a section whose parent is the chapter section

  Scenario: h2 parents to the latest h1, else the chapter
    Given a chapter with h1 and h2 headings spread across two Story blocks
    When the source is built
    Then each h2 section's parent_id is the most recent non-consumed h1 section in the file, else the chapter

  Scenario: Duplicate headings get numeric suffixes
    Given a chapter "x" with two headings titled "Notes"
    When the source is built
    Then their ids are "x/notes" and "x/notes-2"

  Scenario: Section text excludes child sections
    Given an h1 section followed by h2 sections
    When the source is built
    Then the h1 section's text_markdown holds only its own blocks up to the next h1/h2, joined with blank lines

  Scenario: Real source sections are well formed
    Given the real pinned source
    When it is built
    Then every chapter has a root section, in manifest order
    And section ids are unique and match the Data Model pattern
    And every parent_id refers to an earlier section
    And order is contiguous from 0
    And moves/basic-moves has parent moves, moves/hack-and-slash has parent moves/basic-moves, moves/bolster has parent moves/special-moves

  Scenario: Manifest mismatch fails the build
    Given a source directory with an XML file not in the manifest, or a manifest file missing from the source
    When the source is built
    Then an IngestionError is raised whose message names the file

  Scenario: Malformed XML fails the build
    Given a source file that is not well-formed XML
    When the source is built
    Then an IngestionError is raised naming the file

  Scenario: Successful CLI run writes three files
    Given the real source and an empty output directory
    When main(["--out", <dir>]) runs
    Then it returns 0
    And sections.json, moves.json and classes.json are written
    And stdout reports the chapter, section, move and class counts and "unknown markup: 0 (threshold 0)"

  Scenario: Unknown markup over the threshold writes nothing
    Given a copy of the real source with <Sparkle>shiny</Sparkle> injected into an Introduction.xml paragraph
    When the CLI runs with the default threshold
    Then it returns 1
    And the output directory has no JSON files
    And stdout lists "tag:Sparkle: 1"

  Scenario: Raised threshold accepts unknown markup and keeps its text
    Given the same modified source
    When the CLI runs with --max-unknown 1
    Then it returns 0
    And "shiny" appears in the introduction section text

  Scenario: Missing source directory
    Given a --source path that does not exist
    When the CLI runs
    Then it exits 2
    And stderr starts with "ingestion: error:"

  Scenario: Committed output is the snapshot
    Given the committed data/normalized/*.json files
    When the real source is rebuilt in memory and serialized
    Then each serialized file equals the committed text byte-for-byte
    And two independent builds serialize identically
    And the real source has no unknown markup
```

## Technical Notes

Implements from the spec:

- **Python Modules & Interfaces → Block flattening and sectioning (`sections.py`)**, steps 1–4; **Assumptions & Decisions** D4 (granularity), D5 (ID scheme, collision suffixes).
- **Data Model → `sections.json`** table (all fields) and the *Data Model* `Section.to_dict()` key order.
- **Python Modules & Interfaces → Public signatures** for `ingestion/pipeline.py`: `IngestionError`, `BuildResult`, `build()`, `serialize()`, `write()`, `DEFAULT_MAX_UNKNOWN = 0`, and the listed `IngestionError` causes. Per *Suggested Story Breakdown* item 2: in this story `build()` has no `overrides` parameter, `moves` and `classes` are empty (so `moves.json`/`classes.json` are `[]`), and `overrides_applied` is 0.
- **Architecture / Design Overview**: build in memory, write only after all gates pass.
- **Configuration**: CLI flags table, exit codes, stdout report format, unknown keys, WARNING logging and `logging.basicConfig`.
- **Validation Rules** rows: Source dir, Manifest, XML, Unknown markup, Section, CLI.
- D13 (committed output is the snapshot), D14 (output format), D18 (Thanks and appendices ingested), D19 (`.gitkeep` kept).
- **Testing** → shared `conftest.py`: `real_build` session fixture (with the `git submodule update --init` hint) and `make_source(tmp_path, files)`.

Files: `ingestion/sections.py`, `ingestion/pipeline.py`, `ingestion/cli.py`, `ingestion/__main__.py`, `ingestion/tests/conftest.py`, `ingestion/tests/test_sections.py`, `ingestion/tests/test_pipeline.py`, and generated, committed `data/normalized/sections.json`, `moves.json` (`[]`), `classes.json` (`[]`).

## Tests

`ingestion/tests/test_sections.py` (all except `test_manifest_matches_real_source_files`, which is in story 001):
- `test_matching_first_h1_is_consumed_as_chapter_heading`
- `test_non_matching_first_h1_becomes_child_section`
- `test_h2_parents_to_latest_h1_else_chapter`
- `test_duplicate_heading_in_chapter_gets_numeric_suffix`
- `test_section_text_excludes_child_sections`
- `test_build_fails_when_source_has_unlisted_file`
- `test_build_fails_when_manifest_file_is_missing`
- `test_build_fails_on_malformed_xml`
- `test_every_chapter_has_a_root_section_in_manifest_order`
- `test_section_ids_unique_and_well_formed`
- `test_parent_ids_resolve_to_earlier_sections`
- `test_order_is_contiguous_from_zero`
- `test_moves_chapter_hierarchy`

`ingestion/tests/test_pipeline.py` (all):
- `test_real_source_has_no_unknown_markup`
- `test_committed_output_matches_fresh_build` (stale-output failure message as in the spec)
- `test_serialization_is_deterministic`
- `test_cli_writes_three_files_and_reports_counts` — with the interim assertion `0 moves (0 rolled), 0 classes` per *Suggested Story Breakdown*; stories 003–004 update it to its final form
- `test_cli_exits_1_and_writes_nothing_when_unknown_markup_exceeds_threshold`
- `test_cli_raised_threshold_accepts_unknown_markup_and_keeps_text`
- `test_cli_exits_2_on_missing_source_dir`

**Priority:** Critical
**Dependencies:** 002-ingestion-pipeline-001-source-notes-manifest-and-markdown-renderer.md
