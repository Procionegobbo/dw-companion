# 004-static-site-001-astro-scaffold-and-data-layer

**Spec:** STORIES/SPECS/004-static-site.md

**As a** maintainer of the Dungeon World Companion
**I want** the `site/` placeholder replaced by an Astro (TypeScript strict) project with a validated, typed loader for the normalized rulebook JSON and a single URL builder
**So that** every page built later reads trustworthy data, a spec 002 shape change fails the build loudly, and section/move URLs follow one stable citation contract

## Acceptance Criteria

```gherkin
Feature: Astro scaffold, rulebook data layer and URL contract

  Background:
    Given specs 001 and 002 are implemented (site/ tooling, CI site job, docs/decisions.md and data/normalized/{sections,moves,classes}.json exist)

  Scenario: Tooling migration keeps the script-name contract
    When I inspect site/package.json
    Then "lint" is "eslint ." and "typecheck" is "astro check"
    And "dev", "build", "preview" and "test" scripts exist as specified
    And engines.node is ">=22.23.4" and site/.nvmrc is still "22"
    And site/src/index.ts no longer exists

  Scenario: Strictness is not lowered
    When I inspect site/tsconfig.json
    Then it extends Astro's strict preset and keeps noUncheckedIndexedAccess true

  Scenario: Committed data loads
    When loadRulebook() is called
    Then it returns 21 moves, 8 classes, at least 37 sections and 37 root sections
    And repeated calls return the same memoised result

  Scenario: Indexes and ordering
    Given the committed data is loaded
    Then sections and each childrenOf list are sorted by order
    And moveBySectionId maps "moves/hack-and-slash" to move "hack-and-slash"
    And classBySectionId maps "fighter" to a class with base_damage "d10"
    And ancestorsOf("moves/hack-and-slash") returns ["moves", "moves/basic-moves"], root first

  Scenario Outline: Invalid data fails with RulebookError
    Given rulebook input with <defect>
    When parseRulebook is called
    Then a RulebookError is thrown

    Examples:
      | defect                                         |
      | an unknown key on a section                    |
      | a dangling parent_id                           |
      | a move whose section_id does not exist         |
      | duplicate section ids                          |
      | a malformed section id "Moves/Hack"            |
      | a move with stat "LUCK"                        |
      | outcomes missing the miss key                  |

  Scenario: All problems reported together
    Given rulebook input with two independent defects
    When parseRulebook is called
    Then one RulebookError is thrown whose message lists both problems

  Scenario: URLs derive only from ids
    Then sectionUrl("fighter") is "/rules/fighter/"
    And sectionUrl("moves/hack-and-slash") is "/rules/moves/hack-and-slash/"
    And moveUrl("hack-and-slash") is "/moves/hack-and-slash/"
    And sectionUrl/moveUrl throw for "Hack and Slash", "../x" and ""
    And every committed section and move maps to a distinct URL

  Scenario: Unit tests run in CI
    When the CI site job runs
    Then "npm test" runs after "npm run typecheck"
    And the typecheck step sets ASTRO_TELEMETRY_DISABLED "1"
    And ci.yml contains no "secrets."

  Scenario: The URL contract is recorded
    When I read docs/decisions.md
    Then ADR-009 states "/rules/<section_id>/" and "/moves/<move_id>/" verbatim
    And says specs 007 (anchor_url) and 008 (citation links, move card) must use them
    And says it extends ADR-005 whose lint/typecheck script names are kept
```

## Technical Notes

Implements:
- Assumptions & Decisions → D1 (URL scheme), D4 (Astro config), D5 (data loading), D7 (Vitest unit suite only), D8 (tooling migration), D9 (engines), D14 (telemetry env on the `typecheck` step).
- Configuration → `site/package.json` rows `engines.node`, `scripts.dev`, `build`, `preview`, `lint`, `typecheck`, `test`; dependencies `astro`, `zod`; devDependencies `@astrojs/check`, `eslint-plugin-astro`, `vitest` (`marked` comes in story 003, `check-links` script in story 005); `site/astro.config.ts`; `site/tsconfig.json`; `site/src/env.d.ts`; `site/eslint.config.js`; `site/vitest.config.ts`; `.gitignore`.
- Data Model → all of it (`site/src/lib/rulebook.ts`, strict Zod schemas, `Rulebook`, `RulebookError`, `parseRulebook`, `loadRulebook`, `ancestorsOf`).
- Validation Rules → all rows.
- URL Contract → all of it (`site/src/lib/urls.ts`).
- Impact on Existing Code → `site/package.json`, `site/package-lock.json`, `site/tsconfig.json`, `site/eslint.config.js`, delete `site/src/index.ts`, `.github/workflows/ci.yml` (only the `npm test` step and typecheck `env` here; `build` and `check-links` steps come in stories 002 and 005), `.gitignore`, `docs/decisions.md`.
- Documentation → `docs/decisions.md` ADR-009.
- Open risks (a), (b) apply: needs spec 002's JSON committed; use the equivalent strict preset if `astro/tsconfigs/strict` differs.

Spec-level prerequisites (other specs, not stories here): 001, 002, and 003 (`astro-feature-builder` agent).

PR must justify each new dependency in one line (Configuration).

## Tests

- `site/tests/unit/rulebook.test.ts` — all cases in Testing: `loads the committed data without errors`, `sorts sections by order`, `childrenOf lists children in order`, `indexes moves by section id`, `indexes classes by section id`, `ancestorsOf returns root first`, `rejects unknown keys`, `rejects a dangling parent_id`, `rejects a move whose section_id does not exist`, `rejects duplicate section ids`, `rejects a malformed section id`, `rejects an invalid stat`, `rejects outcomes missing the miss key`, `reports every problem in one error`.
- `site/tests/unit/urls.test.ts` — `builds section urls from ids`, `builds move urls from ids`, `rejects ids that do not match the pattern`, `every committed section and move maps to a distinct url`.

**Priority:** Critical
**Dependencies:** None
