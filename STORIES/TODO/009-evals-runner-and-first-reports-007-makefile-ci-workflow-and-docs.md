# 009-evals-runner-and-first-reports-007-makefile-ci-workflow-and-docs

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner
**I want** a `make eval` shortcut, a manual-only GitHub workflow that runs evals with repository secrets, and documentation of the harness
**So that** I can run evals locally or in CI without exposing secrets to PR or push workflows, and the decisions behind the numbers are recorded

## Acceptance Criteria

```gherkin
Feature: Makefile, manual eval workflow, compliance test and docs

  Scenario: make eval
    Given the root Makefile
    Then it has exactly the documented content with CONFIG ?= baseline, DATASET ?= all and the single .PHONY target eval
    And BUDGET, when set, is passed as --budget-usd

  Scenario: Workflow is manual only
    Given .github/workflows/evals.yml
    Then it triggers only on workflow_dispatch with inputs config, dataset (choice) and budget_usd
    And it has permissions contents: read and concurrency group "evals" without cancel-in-progress
    And inputs and secrets reach the shell only through env, never inline ${{ }} in run
    And it uploads evals/reports/*.json and *.md as an artifact with if: always()

  Scenario: Secret workflows exempted from the no-secrets test
    Given test_ci_workflows_reference_no_secrets
    Then it skips files in SECRET_WORKFLOWS = frozenset({"evals.yml"})
    And it still fails if the workflows directory has no *.yml
    And it still covers ci.yml

  Scenario: Allow-listed secret workflows are manual only
    When test_secret_workflows_are_manual_only runs
    Then each allow-listed file present contains workflow_dispatch
    And contains none of "pull_request", "push:" or "schedule:"

  Scenario: ci.yml unchanged
    Then .github/workflows/ci.yml is unchanged and secret-free

  Scenario: ADR recorded
    Given docs/decisions.md
    Then it has an "Evaluation harness" ADR with Status: Accepted, numbered as the next free number
    And it states R-LABEL points 1–4 verbatim, the metric definitions summary, the judge rubric and judge ≠ answer rule, the budget formula and defaults, why there is no schedule, the compliance-test exemption, and open risks (c) and (d)

  Scenario: README subsection
    Given README.md
    Then "### Running evals" appears at the end of "## Development"
    And it says labels are owner-reviewed and links evals/README.md
    And it gives `make eval` and `make eval CONFIG=<name> DATASET=router BUDGET=1.50`
    And it notes the manual "Evals" workflow runs the same command and that no number is meaningful before owner review
    And "## Attribution" is untouched

  Scenario: Datasets are still unreviewed at the end of the spec
    When `grep -c '"reviewed": true' evals/datasets/*.jsonl` is re-run
    Then it reports 0 for every file
    And `grep -c '"reviewed": false'` equals each file's line count
```

## Technical Notes

- **D13**, **D14**, **D15**, **D20**.
- **Configuration → `Makefile`** (exact content; recipe line uses a tab).
- **CI Workflow** (all bullets and steps 1–5, action versions as stated).
- **Impact on Existing Code →** `Makefile`, `.github/workflows/evals.yml`, `backend/tests/test_repository_compliance.py` (deliberate test-semantics change), `docs/decisions.md`, `README.md`.
- **Authorization & Security →** CI isolation, script injection.
- **Documentation →** ADR "Evaluation harness" and `README.md` `### Running evals`. (`evals/README.md` was written in story 002.)
- **Success Criteria →** the grep check is re-run at the end of this last story (not a permanent test). No row may be set to `"reviewed": true` (R-LABEL point 2).
- After this story: **pause (milestone 8)** for the owner's review; the Owner-gate Success Criteria are human steps and are not part of any story.

## Tests

- `backend/tests/test_repository_compliance.py`: `test_ci_workflows_reference_no_secrets` (modified), `test_secret_workflows_are_manual_only` (new).

**Priority:** Medium
**Dependencies:** 009-evals-runner-and-first-reports-006-eval-cli.md
