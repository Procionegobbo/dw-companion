# 001-bootstrap-and-tooling-003-site-typescript-placeholder-tooling

**Spec:** STORIES/SPECS/001-bootstrap-and-tooling.md

**As a** developer of dw-companion
**I want** a minimal `site/` package with strict TypeScript type-checking and ESLint, behind stable `lint` and `typecheck` script names
**So that** CI can gate the frontend from day one and spec 004 can swap in Astro without changing CI

## Acceptance Criteria

```gherkin
Feature: Site TypeScript placeholder tooling

  Scenario: Clean install and checks pass
    Given Node 22 (per site/.nvmrc)
    When I run "npm ci", "npm run lint" and "npm run typecheck" from site/
    Then each exits 0 with no findings

  Scenario: Type checking is strict and actually runs
    Given site/src/index.ts
    When I temporarily add "const n: number = \"x\";"
    Then "npm run typecheck" fails
    And after reverting the change it passes again

  Scenario: Script-name contract for spec 004
    Given site/package.json
    Then it defines the scripts "lint" as "eslint ." and "typecheck" as "tsc --noEmit"

  Scenario: Package configuration
    Given site/package.json
    Then name is "dw-companion-site", private is true, type is "module" and engines.node is ">=22"
    And devDependencies typescript, eslint, @eslint/js and typescript-eslint are present with caret ranges written by "npm install --save-dev"
    And site/package-lock.json is committed

  Scenario: No Astro and no formatter yet
    Given site/
    Then no Astro dependency and no Prettier configuration are present

  Scenario: Decision recorded
    Given docs/decisions.md
    Then ADR-005 "Frontend placeholder tooling: npm, tsc strict, ESLint" is appended in the D15 format, including the script-name contract
```

## Technical Notes

Implements:
- Assumptions & Decisions → D11.
- Configuration → `site/tsconfig.json`, `site/package.json`, `site/eslint.config.js`, `site/.nvmrc`.
- Impact on Existing Code → rows `site/package.json`, `site/package-lock.json`, `site/tsconfig.json`, `site/eslint.config.js`, `site/.nvmrc`, `site/src/index.ts` (exact placeholder comment + `export {};`).
- Site Toolchain & Commands.
- Documentation Stubs → `docs/decisions.md` row ADR-005 (append; ADRs are never renumbered).

The spec's Suggested Story Breakdown notes this story explicitly requires touching `site/`, which `python-feature-builder` handles only when a story requires it.

Files touched: `site/package.json`, `site/package-lock.json`, `site/tsconfig.json`, `site/eslint.config.js`, `site/.nvmrc`, `site/src/index.ts`, `docs/decisions.md`.

## Tests

Manual / CI verification from the spec's Testing section: `npm run lint` and `npm run typecheck` exit 0; a deliberate type error in `site/src/index.ts` makes `npm run typecheck` fail (check once, then revert).

**Priority:** High
**Dependencies:** 001-bootstrap-and-tooling-002-source-submodule-licensing-and-docs.md (ordering only: appends to `docs/decisions.md`, created there)
