# 004-static-site-002-layout-home-and-404

**Spec:** STORIES/SPECS/004-static-site.md

**As a** reader of the rules
**I want** a home page listing every chapter, a shared header and attribution footer on every page, and a not-found page
**So that** I can start navigating the rulebook and always see who wrote the text and under what licence

## Acceptance Criteria

```gherkin
Feature: Base layout, home and 404

  Scenario: Build produces the home page
    When I run "npm run build" in site/
    Then dist/index.html and dist/404.html exist

  Scenario: Home lists every chapter
    When I open dist/index.html
    Then its title is "Dungeon World Companion (unofficial)"
    And it has h1 "Dungeon World Companion" and the intro paragraph from the spec
    And under h2 "Chapters" an ordered list links every section with parent_id null, in order, by title, to sectionUrl(id)
    And under h2 "Moves" the text "Basic and special moves" links to "/moves/"

  Scenario: Layout on every page
    When I open any built page
    Then it has <html lang="en">, a charset and viewport meta
    And a "Skip to content" link to "#main" that is hidden until focused
    And a header with the site name linking to "/" and nav "Main" with "Contents" → "/" and "Moves" → "/moves/"
    And the nav link for the current page has aria-current="page"
    And the content is inside <main id="main">

  Scenario: Attribution footer on every page
    When I open any built page
    Then the footer contains exactly the spec's copy: CC BY 3.0 credit with links to github.com/Sagelt/Dungeon-World and the CC BY 3.0 licence, the adaptation statement, the SRD 5.1 / CC BY 4.0 notice, the unofficial statement and the MIT-for-code statement
    And the two licence links have rel="license"
    And there is no link to this project's own repository

  Scenario: Not-found page
    When I open dist/404.html
    Then its title is "Page not found · Dungeon World Companion"
    And it has h1 "Page not found", the text "There is no page at this address." and a link "Go to the contents" → "/"

  Scenario: Page titles
    Then pageTitle("X") is "X · Dungeon World Companion"
    And pageTitle() is "Dungeon World Companion (unofficial)"

  Scenario: Build runs in CI
    When the CI site job runs
    Then "npm run build" runs after "npm test" with ASTRO_TELEMETRY_DISABLED "1"
```

## Technical Notes

Implements:
- Pages & Components → `BaseLayout.astro`, `SiteHeader.astro`, `SiteFooter.astro` (footer copy is exact), `global.css`, `index.astro`, `404.astro`, and the `rollLabel` / `categoryLabel` / `pageTitle` copy for `format.ts`.
- Assumptions & Decisions → D10 (footer), D14 (telemetry env on the `build` step).
- Impact on Existing Code → `site/src/lib/format.ts`, `site/src/layouts/BaseLayout.astro`, `site/src/components/SiteHeader.astro`, `site/src/components/SiteFooter.astro`, `site/src/styles/global.css`, `site/src/pages/index.astro`, `site/src/pages/404.astro`, `.github/workflows/ci.yml` (`npm run build` step only).
- All links use `HOME_URL`, `MOVES_INDEX_URL`, `sectionUrl` from `urls.ts` (story 001). The `/moves/` page itself arrives in story 004; the link is expected to dangle until then (link check runs in story 005).

## Tests

- `site/tests/unit/format.test.ts` — `rollLabel maps every stat`, `categoryLabel maps every category`, `pageTitle with and without a title`.

**Priority:** High
**Dependencies:** 004-static-site-001-astro-scaffold-and-data-layer.md
