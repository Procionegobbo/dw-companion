# 012-readme-polish-and-launch-003-owner-gate-fill-slots-and-launch

**Spec:** STORIES/SPECS/012-readme-polish-and-launch.md

> **Owner checklist — not a feature-builder story.** Performed by the project owner as each upstream owner gate completes. A feature-builder run must not fill any slot or invent any value.

**As a** project owner
**I want** to fill the five `TODO-OWNER` slots from committed sources and run the launch check
**So that** the README shows only measured, committed evidence and milestone 11 is accepted

## Acceptance Criteria

```gherkin
Feature: Owner fills README slots and launches

  Scenario: Fill demo-url
    Given spec 011 owner gate step 8 has written the "Live URL:" line in docs/deploy.md
    When the owner fills the demo-url slot
    Then every TODO-OWNER(demo-url) is replaced with that URL as an autolink and the demo-url HTML comment is deleted

  Scenario: Fill eval-results, eval-comparison and cost-latency from one comparison file
    Given spec 010 owner gate steps 6-7 have committed the comparison file under evals/reports/comparisons/ and the tuning ADR
    When the owner fills eval-results, eval-comparison and cost-latency
    Then all three are filled from the same committed comparison file (chosen configuration's column), not from raw report JSON, except models, report path and date which come from the chosen report JSON
    And values are copied exactly as spec 010's formatter printed them, with no rounding or re-computation
    And the eval-comparison block is pasted with both comparison-table marker comments, followed by the "Chosen:" line linking the comparison file and the tuning ADR
    And each slot's HTML comment and every TODO-OWNER(<id>) occurrence for that slot is removed

  Scenario: Record and fill demo-gif
    Given the production configuration is deployed on the live URL
    When the owner records docs/media/demo.gif
    Then it is at most 20 s and at most 5 MB and shows one rules question with a citation click and one action description with "Roll the dice for me" ticked
    And it shows no API keys, Langfuse UI, browser profile or personal data
    And the demo-gif pending line is replaced with the image line from the slot comment and the comment is deleted

  Scenario: Launch check
    When all five slots are filled
    Then `grep -n "TODO-OWNER" README.md` prints nothing
    And `uv run pytest` passes, including test_readme_relative_links_resolve (proving docs/media/demo.gif and linked report files exist)
    And every value in the results, comparison and cost/latency tables matches the committed comparison file cell for cell
    And the owner reads the rendered README on GitHub once, top to bottom

  Scenario: Configuration changes after launch
    Given a later tuning round changes the production configuration
    Then eval-results, eval-comparison and cost-latency are refilled from the new comparison file
```

## Technical Notes

- Implements: *Owner Gate* (steps 1–5), *Placeholder Slots and Owner Fill Procedure* (slot registry and fill rules 1–5), *Success Criteria* → Owner (milestone 11 acceptance), and *Assumptions & Decisions* D5, D6, D10.
- Slots may be filled in any order and in separate commits (`docs(readme): fill <slot-id>`).
- *Authorization & Security*: demo GIF content restrictions.
- Touches `README.md` and creates `docs/media/demo.gif`.

## Tests

No automated test case is added. The owner runs the launch check: `grep -n "TODO-OWNER" README.md` prints nothing and `uv run pytest` passes.

**Priority:** High
**Dependencies:** 012-readme-polish-and-launch-001-readme-rewrite-and-development-guide.md, 012-readme-polish-and-launch-002-readme-guard-tests.md (plus spec 010's and spec 011's owner gates)
