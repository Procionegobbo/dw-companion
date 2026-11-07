# 001-bootstrap-and-tooling-004-ci-workflow

**Spec:** STORIES/SPECS/001-bootstrap-and-tooling.md

**As a** project owner
**I want** a GitHub Actions workflow that runs the Python and site checks on every pull request and on pushes to `main`, with no access to secrets
**So that** regressions are caught before merge and CI can never call a paid API

## Acceptance Criteria

```gherkin
Feature: CI workflow

  Scenario: Triggers and permissions
    Given .github/workflows/ci.yml named "CI"
    Then it triggers on pull_request (all branches) and on push to main
    And it never uses pull_request_target
    And top-level permissions are "contents: read"
    And concurrency group is "ci-${{ github.ref }}" with cancel-in-progress true

  Scenario: No secrets in workflows
    Given every *.yml file in .github/workflows/
    Then none contains "secrets."
    And no credential-bearing env is defined anywhere in ci.yml

  Scenario: Secrets test cannot pass vacuously
    Given .github/workflows/ is missing or contains no *.yml file
    When test_ci_workflows_reference_no_secrets runs
    Then it fails

  Scenario: Python job
    Given the "python" job on ubuntu-latest with timeout-minutes 10
    Then its steps in order are: actions/checkout@v7 with submodules true; astral-sh/setup-uv@v10 with enable-cache true; then install, format check, lint, type check and tests as five separately named steps using the commands from Python Toolchain & Commands

  Scenario: Site job
    Given the "site" job on ubuntu-latest with timeout-minutes 10 and working-directory site
    Then it uses actions/checkout@v7 without submodules
    And actions/setup-node@v7 with node-version-file site/.nvmrc, cache npm and cache-dependency-path site/package-lock.json
    And runs "npm ci", "npm run lint" and "npm run typecheck"

  Scenario: Both jobs green on a pull request
    Given a pull request containing this feature
    When CI runs
    Then both the "python" and "site" jobs pass

  Scenario: Decision recorded
    Given docs/decisions.md
    Then ADR-006 "CI scope and the no-paid-API rule" is appended in the D15 format, sourced from D12 and D13
```

## Technical Notes

Implements:
- Assumptions & Decisions → D12, D13.
- CI Workflow (whole section).
- Impact on Existing Code → row `.github/workflows/ci.yml`.
- Validation Rules → row `CI`.
- Authorization & Security → CI read-only permissions, no secrets, `pull_request` trigger.
- Documentation Stubs → `docs/decisions.md` row ADR-006 (append).
- Testing → `test_ci_workflows_reference_no_secrets` added to the existing `backend/tests/test_repository_compliance.py`.

Files touched: `.github/workflows/ci.yml`, `backend/tests/test_repository_compliance.py`, `docs/decisions.md`.

## Tests

- `test_ci_workflows_reference_no_secrets` in `backend/tests/test_repository_compliance.py`.
- Manual: open a PR and confirm both CI jobs (`python`, `site`) are green.

**Priority:** High
**Dependencies:** 001-bootstrap-and-tooling-001-python-skeleton-and-toolchain.md, 001-bootstrap-and-tooling-002-source-submodule-licensing-and-docs.md, 001-bootstrap-and-tooling-003-site-typescript-placeholder-tooling.md
