# 012-readme-polish-and-launch-002-readme-guard-tests

**Spec:** STORIES/SPECS/012-readme-polish-and-launch.md

**As a** project maintainer
**I want** offline tests that guard the README's structure, links, ADR references, placeholder hygiene and command drift
**So that** future edits cannot silently break the README, leak unmanaged placeholders or fabricate slot ids, while unfilled owner slots never turn CI red

## Acceptance Criteria

```gherkin
Feature: README guard tests

  Scenario: Guards pass on the committed README and development guide
    Given story 001's README.md and docs/development.md are committed
    When "uv run pytest backend/tests/test_readme.py" runs
    Then every test passes
    And the tests read files only and make no network call

  Scenario: Guards pass whether or not owner slots are filled
    Given README.md still contains TODO-OWNER(<id>) tokens for the five slot ids
    When the placeholder test runs
    Then it passes
    And it would also pass once every slot is filled and no TODO-OWNER token remains

  Scenario: Section order is enforced
    Given a text with "## Live demo" before "## The problem"
    When the heading check runs on it
    Then the problem is reported

  Scenario: Broken relative links are reported, external and hidden links are not
    Given a tmp_path document containing "[x](missing.md)"
    When the link check runs
    Then "missing.md" is reported
    And "[x](https://example.com)", "[x](#anchor)", a link inside a fenced block and a link inside an HTML comment are not reported
    And a link with a fragment (e.g. "evals/README.md#tuning-round") is checked for the file only

  Scenario: Unknown ADR numbers are reported
    Given a decisions text containing only "## ADR-001: ..."
    When the ADR check runs on a text referencing "ADR-999"
    Then "ADR-999" is reported
    And the repo test also fails if the README references no ADR at all

  Scenario: Bad placeholder tokens are reported
    When the placeholder check runs on "TODO-OWNER(demo_gif)", a bare "TODO", "TBD" and "{{adr:graph}}"
    Then each is reported
    And "TODO-OWNER(demo-url)" is not reported

  Scenario: Nested HTML comments are reported
    When the comment check runs on "<!-- a <!-- b --> c -->"
    Then it is reported
    And the comparison markers "<!-- comparison-table:start -->" and "<!-- comparison-table:end -->" pass
```

## Technical Notes

- Implements: *Testing* (entire section: helpers, nine repo tests, five negative tests, edge cases) and *Validation Rules* (all rows not marked *(review)*); *Assumptions & Decisions* D11 (one new file, never fails on unfilled slots).
- New file `backend/tests/test_readme.py` only, using the spec 001 `REPO_ROOT` pattern stated in *Testing*. `OWNER_SLOTS` is exactly the five slot ids in *Testing*.
- Check logic lives in private pure functions returning a list of problems; negative tests use inline strings and `tmp_path`, never the real README (*Testing*).
- *Validation Rules* → Development guide: if a built `### ` heading differs from the pinned text, the built text wins; update the test constant and note it in the PR.
- *Impact on Existing Code*: `backend/tests/test_repository_compliance.py` stays unchanged.

## Tests

From *Testing*:
- `test_readme_sections_in_required_order`
- `test_readme_attribution_states_licensing_split`
- `test_readme_relative_links_resolve`
- `test_development_doc_links_resolve`
- `test_readme_adr_references_exist`
- `test_readme_has_no_unmanaged_placeholders`
- `test_readme_html_comments_are_well_formed`
- `test_readme_reproduction_commands_match_makefile`
- `test_development_doc_has_moved_sections`
- `test_heading_check_rejects_wrong_order`
- `test_link_check_reports_missing_file`
- `test_adr_check_reports_unknown_number`
- `test_placeholder_check_rejects_bad_tokens`
- `test_comment_check_rejects_nested_comment`

Manual (from *Testing*): read the README rendered on GitHub or a Markdown preview to check tables and diagrams render.

**Priority:** High
**Dependencies:** 012-readme-polish-and-launch-001-readme-rewrite-and-development-guide.md
