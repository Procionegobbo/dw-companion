# 004-static-site-003-section-pages

**Spec:** STORIES/SPECS/004-static-site.md

**As a** reader of the rules
**I want** one page per rulebook section with its rendered text, breadcrumbs, child sections and previous/next links
**So that** I can read any chapter sequentially and the assistant can cite any section by a stable URL

## Acceptance Criteria

```gherkin
Feature: Section pages and Markdown rendering

  Scenario: One page per section
    When I run "npm run build"
    Then for every section there is dist/rules/<section_id>/index.html
    And it contains <article data-section-id="<section_id>"> with an h1 equal to the section title

  Scenario: Breadcrumbs
    When I open dist/rules/moves/hack-and-slash/index.html
    Then the "Breadcrumb" nav lists "Contents" → "/", then "/rules/moves/" and "/rules/moves/basic-moves/" by title
    And ends with the current title as plain text with aria-current="page"

  Scenario: Class chapters show stats
    When I open dist/rules/fighter/index.html
    Then a dl.class-stats shows "Max HP" → "10 + Constitution", "Base damage" → "d10", "Load" → "12 + Str"

  Scenario: Child sections
    Given a section that has children
    When I open its page
    Then h2 "In this section" lists links to each child by title, in order
    And a section without children has no such heading

  Scenario: Previous and next
    When I open a section page
    Then the "Previous and next" nav after the article links "← <previous title>" and "<next title> →" in global order
    And the first section has no previous link and the last has no next link

  Scenario: Markdown renders as HTML
    Then emphasis, strong, lists, GFM tables, blockquotes and h4 headings render
    And backslash escapes like "b\[2d6\] \_\_" render as "b[2d6] __"
    And empty input renders as ""

  Scenario: Raw HTML is escaped
    When the Markdown contains "<script>alert(1)</script>"
    Then the output contains "&lt;script&gt;" and no "<script>"
```

## Technical Notes

Implements:
- Markdown Rendering → all of it (`site/src/lib/markdown.ts`); Assumptions & Decisions → D6; adds the `marked` dependency (Configuration → `dependencies`).
- Pages & Components → `rules/[...id].astro` items 1, 2, 3, 5, 6, 7. Item 4 (the "Move card:" link) is out of this slice — added in story 004.
- Assumptions & Decisions → D2 (page per section), D12 (class stat block).
- Authorization & Security → `set:html` only with `renderMarkdown` output.
- Uses `loadRulebook`, `ancestorsOf`, `childrenOf`, `classBySectionId` (story 001) and `sectionUrl`.
- Files: `site/src/lib/markdown.ts`, `site/src/pages/rules/[...id].astro`, `site/tests/unit/markdown.test.ts`, `site/package.json`, `site/package-lock.json`.

## Tests

- `site/tests/unit/markdown.test.ts` — `renders emphasis and strong`, `renders bulleted and numbered lists`, `renders a GFM table`, `renders blockquotes and h4 headings`, `unescapes backslash escapes`, `escapes raw html`, `returns empty string for empty input`.

**Priority:** High
**Dependencies:** 004-static-site-002-layout-home-and-404.md
