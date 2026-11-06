# 002-ingestion-pipeline-001-source-notes-manifest-and-markdown-renderer

**Spec:** STORIES/SPECS/002-ingestion-pipeline.md

**As a** maintainer of the dw-companion ingestion pipeline
**I want** the source XML documented, the chapter manifest defined, and a tolerant, loud Markdown renderer for the source's markup
**So that** every later parsing step turns the pinned Dungeon World text into faithful Markdown and any unexpected markup is counted instead of silently lost

## Acceptance Criteria

```gherkin
Feature: Source notes, chapter manifest and Markdown renderer

  Scenario: Source notes document the pinned source
    Given the submodule vendor/dungeon-world/ at the pinned commit
    When I open docs/source-notes.md
    Then it is titled "# Source notes"
    And it contains the sections "Pinned source", "File layout", "Tag and attribute inventory",
        "Inconsistencies found", "Special characters" and "Unknown-markup gate"
    And their facts have been re-verified against the submodule

  Scenario: Manifest matches the real source files
    Given the 37 chapters listed in CHAPTERS in ingestion/manifest.py, in book order
    When the set of manifest files is compared with every **/*.xml under vendor/dungeon-world/text
    Then the two sets are equal
    And CLASS_CHAPTER_IDS lists bard, cleric, druid, fighter, paladin, ranger, thief, wizard

  Scenario: Inline markup renders as Markdown
    Given a paragraph containing em, strong and Strong elements
    When it is rendered inline
    Then em becomes *…*, strong and Strong become **…**
    And a span with aid:cstyle "Tags" is italic, while a span with cstyle "SpellName" or no cstyle is plain

  Scenario: Text is normalised and escaped
    Given text containing tabs, whitespace runs, "✴" and U+200B
    When it is rendered inline
    Then whitespace runs collapse to one space, "✴" and U+200B are removed
    And "\", "*", "_", "`", "[", "]" are backslash-escaped while emitted emphasis markers are not
    And a leading block marker ("#", ">", "-"/"+"/"*" followed by a space, or a number followed by "." or ")" and a space) is escaped

  Scenario: Block styles render per the rendering table
    Given paragraphs with pstyle MonsterName, SpellName or MagicItem
    Then they render as "#### " headings
    Given paragraphs with pstyle Example, ExampleDialogue, ExampleDialogueFirstLine or ExampleDialogueLastLine
    Then they render as "> " blockquotes
    Given a paragraph with pstyle Requirement
    Then it renders italic
    Given ul and ol lists
    Then ul items render as "- " lines and ol items as "1. ", "2. "… restarting per list

  Scenario: The stat table renders as a GFM table
    Given a StatTable whose children mix Cell, TableHeader and TableBody wrappers
    When it is rendered
    Then the header row is "| Score | Modifier |" followed by "| --- | --- |"
    And the remaining cells fill body rows left to right using aid:tcols columns

  Scenario: Loose container text becomes a paragraph
    Given non-whitespace text directly inside a container element
    When it is rendered
    Then it becomes an inline-normalised paragraph

  Scenario: Unknown markup is counted and its text kept
    Given a paragraph containing an unknown tag, attribute, pstyle or cstyle
    When it is rendered
    Then the text is still rendered
    And UnknownMarkup records the occurrence under "tag:<name>", "attr:<name>", "pstyle:<value>" or "cstyle:<value>"
    And a WARNING is logged on logger "ingestion"

  Scenario: Slugs are stable and ASCII
    Given a heading title
    When slugify is applied
    Then the result is NFKD-normalised, accent-free, lowercase, with apostrophes deleted,
        "&" replaced by "and", and every run of other characters replaced by "-"
```

## Technical Notes

Implements from the spec:

- **Documentation → `docs/source-notes.md`**, sections 1–5 and 8 (sections 6–7 belong to story 003). Facts come from *Source Facts* and D3/D12/D14, re-verified against the submodule (D1).
- **Chapter Manifest** → `CHAPTERS` (all 37 rows) and `CLASS_CHAPTER_IDS`; **Impact on Existing Code → `ingestion/manifest.py`** (`Chapter(file, id, title)`).
- **Data Model** → all dataclasses and the `Category`/`Stat` literals in `ingestion/models.py`, types and `to_dict()` key order only (no extraction logic).
- **Python Modules & Interfaces → Markdown rendering (`markdown.py`)**: the Inline table, the Blocks table, block-marker escaping, *Unknown tracking*, `slugify(text)`, `plain_text(el)`; known inventories exactly as in *Source Facts* (tags, attributes, 29 pstyles, 2 cstyles).
- **Configuration → `pyproject.toml`**: the additive `[tool.ruff.lint.per-file-ignores]` block (D17).
- D2: stdlib only.

Files: `docs/source-notes.md`, `ingestion/manifest.py`, `ingestion/models.py`, `ingestion/markdown.py`, `ingestion/tests/__init__.py`, `ingestion/tests/test_markdown.py`, `pyproject.toml`. `test_manifest_matches_real_source_files` is listed under `test_sections.py` in *Testing* and needs `SOURCE_DIR` from `conftest.py`; this story creates those files with only what that test needs (`REPO_ROOT`, `SOURCE_DIR`); story 002 adds the rest.

## Tests

`ingestion/tests/test_markdown.py` (all, per *Testing*):
- `test_emphasis_tags_render_as_markdown`
- `test_whitespace_star_glyph_and_zero_width_space_are_normalised`
- `test_markdown_metacharacters_are_escaped`
- `test_leading_block_marker_is_escaped`
- `test_tags_span_is_italic_and_spellname_span_is_plain`
- `test_monster_spell_and_magic_item_paragraphs_render_as_h4`
- `test_example_paragraphs_render_as_blockquote`
- `test_requirement_paragraph_renders_italic`
- `test_lists_render_bulleted_and_numbered`
- `test_stat_table_with_mixed_cell_tags_renders_gfm_table`
- `test_loose_container_text_becomes_paragraph`
- `test_unknown_tag_is_counted_and_its_text_kept`
- `test_unknown_attribute_pstyle_and_cstyle_are_counted`
- `test_slugify` (parametrized cases as in the spec)

`ingestion/tests/test_sections.py`:
- `test_manifest_matches_real_source_files` (real)

**Priority:** Critical
**Dependencies:** None (requires spec 001 to be implemented)
