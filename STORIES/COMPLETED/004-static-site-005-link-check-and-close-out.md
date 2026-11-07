# 004-static-site-005-link-check-and-close-out

**Spec:** STORIES/SPECS/004-static-site.md

**As a** maintainer
**I want** an automated check over the built site proving every section and move resolves, every internal link works and every page carries the attribution footer
**So that** the citation contract and licence compliance are enforced in CI (milestone 3 acceptance)

## Acceptance Criteria

```gherkin
Feature: Built-output link and content check

  Scenario: Check passes on the real site
    Given "npm run build" has run
    When I run "npm run check-links"
    Then checkSite("dist", loadRulebook()) reports zero problems and the command exits 0

  Scenario: Missing build fails loudly
    Given site/dist/index.html does not exist
    When I run "npm run check-links"
    Then it fails with "site/dist not found: run `npm run build` first" (not skipped)

  Scenario Outline: Checker reports defects
    Given a synthetic dist with <defect>
    When checkSite runs
    Then problems contains a message naming the file and offending href or id

    Examples:
      | defect                                   |
      | a missing section page                   |
      | a page without its id marker             |
      | a missing move page                      |
      | a broken internal link                   |
      | a link missing its trailing slash        |
      | a fragment with no matching id           |
      | a relative or //host link                |
      | a page without the attribution footer    |

  Scenario: External links are not fetched
    Given a synthetic dist with http:, https: and mailto: links
    When checkSite runs
    Then they produce no problems and no network request is made

  Scenario: Counts
    Given a complete synthetic site
    Then pages equals the number of HTML files and internalLinks the number of checked internal hrefs

  Scenario: CI and docs
    Then the CI site job runs "npm run check-links" after "npm run build"
    And the README Development block lists npm ci, dev, lint, typecheck, test, build, check-links (after build)
    And the README requirements line says "Node 22.23.4 or newer 22.x"
    And the README Attribution section is unchanged
```

## Technical Notes

Implements:
- Link Check → all of it (`site/src/lib/link-check.ts`, rules 1–3, `LinkCheckReport`, `checkSite`).
- Assumptions & Decisions → D7 (dist suite, fail-not-skip).
- Configuration → `scripts.check-links`, `site/vitest.dist.config.ts`.
- Impact on Existing Code → `.github/workflows/ci.yml` (`npm run check-links` step), `README.md`.
- Documentation → `README.md`.
- Files: `site/src/lib/link-check.ts`, `site/vitest.dist.config.ts`, `site/package.json`, `site/tests/unit/link-check.test.ts`, `site/tests/dist/site.test.ts`, `.github/workflows/ci.yml`, `README.md`.

## Tests

- `site/tests/unit/link-check.test.ts` — `passes a complete site`, `reports a missing section page`, `reports a page without its id marker`, `reports a missing move page`, `reports a broken internal link`, `reports a missing trailing slash`, `reports a missing fragment target`, `reports a relative link`, `skips external links`, `reports a page without the attribution footer`.
- `site/tests/dist/site.test.ts` — `every section_id and move_id resolves and every internal link works`, `home links every chapter`, `moves index links every move`, `hack-and-slash card shows trigger, roll, bands and unstated miss`, `last-breath card shows its miss`, `encumbrance card has no outcomes block`, `move section links back to its card`, `breadcrumbs list ancestors`, `fighter chapter shows class stats`, `stat table renders as html table`, `every page declares lang and has a main landmark`.

**Priority:** Critical
**Dependencies:** 004-static-site-004-move-pages.md
