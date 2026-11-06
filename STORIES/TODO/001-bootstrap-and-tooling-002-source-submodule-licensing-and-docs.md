# 001-bootstrap-and-tooling-002-source-submodule-licensing-and-docs

**Spec:** STORIES/SPECS/001-bootstrap-and-tooling.md

**As a** project owner publishing an unofficial Dungeon World companion
**I want** the rules source pinned as a submodule, with complete licensing, attribution, README stub, decision log and `.env.example`, all guarded by compliance tests
**So that** the CC BY 3.0 (and SRD 5.1) obligations are met verifiably from day one and later specs have a fixed source and documented conventions

## Acceptance Criteria

```gherkin
Feature: Source submodule, licensing and docs

  Scenario: Source is pinned as a submodule
    Given the repository
    When I run "git submodule status"
    Then vendor/dungeon-world is at commit e67bd51c09d24518a7f989149b76094fbcc7fecc
    And .gitmodules has one entry with path "vendor/dungeon-world" and URL "https://github.com/Sagelt/Dungeon-World"

  Scenario: Vendored source is checked out
    Given a clone with submodules initialised
    When the compliance tests run
    Then vendor/dungeon-world/LICENSE exists and contains "Creative Commons Attribution 3.0"

  Scenario: Submodule not initialised
    Given a clone where vendor/dungeon-world/LICENSE is missing
    When the compliance tests run
    Then test_vendored_source_is_checked_out fails with a message suggesting "git submodule update --init"

  Scenario: Attribution is complete
    Given ATTRIBUTION.md
    Then its content matches the exact text in the spec
    And it contains "Sage LaTorra", "Adam Koebel", "https://github.com/Sagelt/Dungeon-World", "https://creativecommons.org/licenses/by/3.0/", "unofficial", "adapted", "SRD 5.1", "https://creativecommons.org/licenses/by/4.0/legalcode" and "e67bd51c09d24518a7f989149b76094fbcc7fecc"

  Scenario: Licence is verbatim MIT
    Given LICENSE
    Then its first line is "MIT License"
    And it contains "Copyright (c) 2026 Federico Maiorini"
    And the body is the unmodified standard MIT text

  Scenario: README stub has an Attribution section
    Given README.md
    Then its content matches the exact stub text in the spec
    And it has a line exactly "## Attribution" whose section (up to the next "## " heading) contains "ATTRIBUTION.md" and "unofficial"

  Scenario: .env.example declares keys without values
    Given .env.example with the exact content in the spec
    Then every non-blank, non-comment line matches ^[A-Z][A-Z0-9_]*=$
    And keys are unique
    And the keys are exactly MODEL_ROUTER, MODEL_CLASSIFIER, MODEL_ANSWER, MODEL_EMBEDDINGS

  Scenario: .env.example contains a value
    Given a .env.example line such as "MODEL_ROUTER=gpt"
    When the compliance tests run
    Then test_env_example_declares_keys_without_values fails

  Scenario: Decision log and doc stubs exist
    Given docs/decisions.md
    Then it has the title "# Decisions", the intro paragraph, and ADR-001 through ADR-004 in the D15 format with Status "Accepted" and the implementation date
    And ADR-003 includes the full commit hash and the upstream URL
    And docs/source-notes.md and docs/architecture.md exist with the specified one-line stubs
```

## Technical Notes

Implements:
- Assumptions & Decisions → D7, D8, D9, D10, D14, D15.
- Configuration → `.env.example` (exact content).
- Impact on Existing Code → rows `.gitmodules`, `vendor/dungeon-world`, `.env.example`, `LICENSE`, `ATTRIBUTION.md`, `README.md`, `docs/decisions.md`, `docs/source-notes.md`, `docs/architecture.md`, `backend/tests/test_repository_compliance.py`.
- Attribution & Licensing Files → `ATTRIBUTION.md`, `README.md`, `LICENSE` (exact texts).
- Documentation Stubs → `docs/decisions.md` rows ADR-001 to ADR-004 only; `docs/source-notes.md`; `docs/architecture.md`.
- Validation Rules → rows `.env.example`, `ATTRIBUTION.md`, `README.md`, `LICENSE`, `Submodule` (the `CI` row belongs to story 004).
- Authorization & Security → `.env` git-ignored / `.env.example` keys only; public HTTPS submodule URL.

Add the submodule with `git submodule add` (D7 URL, then check out the pinned commit). Nothing outside `vendor/dungeon-world/text/` is read (D10).

Files touched: `.gitmodules`, `vendor/dungeon-world`, `LICENSE`, `ATTRIBUTION.md`, `README.md`, `.env.example`, `docs/decisions.md`, `docs/source-notes.md`, `docs/architecture.md`, `backend/tests/test_repository_compliance.py`.

## Tests

`backend/tests/test_repository_compliance.py` (all except `test_ci_workflows_reference_no_secrets`, which is story 004):
- `test_attribution_credits_authors_source_and_license`
- `test_attribution_states_adaptation_and_unofficial_status`
- `test_attribution_reproduces_srd_notice`
- `test_attribution_records_pinned_commit`
- `test_license_is_mit`
- `test_readme_has_attribution_section`
- `test_vendored_source_is_checked_out`
- `test_env_example_declares_keys_without_values`

**Priority:** Critical
**Dependencies:** 001-bootstrap-and-tooling-001-python-skeleton-and-toolchain.md
