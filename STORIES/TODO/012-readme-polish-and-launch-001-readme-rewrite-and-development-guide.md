# 012-readme-polish-and-launch-001-readme-rewrite-and-development-guide

**Spec:** STORIES/SPECS/012-readme-polish-and-launch.md

**As a** hiring manager reading the repository
**I want** a README that explains the problem, the demo, where AI is and is not used, the architecture, the evaluation, cost/latency/guardrails, trade-offs, next steps and attribution, in that order
**So that** I can judge the project's production-minded AI engineering from one page, with every unmeasured value visibly marked as pending rather than invented

## Acceptance Criteria

```gherkin
Feature: Final README and moved development guide

  Background:
    Given specs 001 to 011 are built (their owner gates need not be complete)
    And README.md holds spec 001's stub plus the "## Development" section extended by specs 004, 007, 008, 009, 010 and 011

  Scenario: Development commands move verbatim to docs/development.md
    When the story is complete
    Then docs/development.md exists and its first line is "# Development"
    And under the title is the one-line intro "Commands for working on dw-companion locally. The project overview is in the [README](../README.md)."
    And each former "### " subsection of the README's "## Development" section is a "## " heading, with its content otherwise unchanged
    And it contains "## Running the assistant locally", "## Running the API and chat widget locally", "## Running evals", "## Running the container and deploying" and "uv run pytest"
    And every relative link is rewritten for the docs/ location (e.g. "docs/decisions.md" -> "decisions.md", "evals/README.md" -> "../evals/README.md") and resolves to an existing file or directory

  Scenario: README has exactly the nine handoff sections in order
    When README.md is rewritten from the spec's README Content template
    Then its "## " headings outside fenced code are exactly, in order: "The problem", "Live demo", "What the assistant does (and what it doesn't do with AI)", "Architecture", "Evaluation", "Cost, latency and guardrails", "Trade-offs and decisions", "What I'd do next", "Attribution"
    And README.md has no "## Development" heading, no "## License" heading and no "> Status: under construction." line
    And the Architecture section ends with links to docs/architecture.md and docs/development.md

  Scenario: Attribution keeps spec 001 compliance and carries the licensing split
    When README.md is rewritten
    Then the "## Attribution" heading text is unchanged
    And that section contains "Sage LaTorra", "Adam Koebel", "https://github.com/Sagelt/Dungeon-World", "CC BY 3.0", "adapted", "unofficial", "MIT", "ATTRIBUTION.md" and "LICENSE"
    And spec 001's test_readme_has_attribution_section passes unmodified

  Scenario: Every ADR reference token is resolved
    Given each {{adr:<key>}} token in the template maps to an ADR title in the spec's ADR Reference Tokens table
    When README.md is written
    Then every token is replaced by "ADR-NNN" taken from the matching "## ADR-NNN: <title>" heading in docs/decisions.md
    And each ADR link targets docs/decisions.md with no heading anchor
    And README.md contains no "{{", no "}}" and no "TBD"
    And any ADR title matched by originating spec rather than exact wording is listed in the PR description

  Scenario: The five owner-gated slots are preserved exactly
    When README.md is written
    Then every TODO-OWNER(...) HTML comment, visible pending line and table cell from the template is kept exactly as written
    And `grep -o "TODO-OWNER([a-z-]*)" README.md | sort -u` lists exactly demo-url, demo-gif, eval-results, eval-comparison and cost-latency
    And every "TODO" in README.md is the start of "TODO-OWNER(<id>)" with one of those five ids
    And every "<!--" is closed by "-->" before the next "<!--"

  Scenario: No fabricated values
    When README.md is written
    Then no visible slot line or table cell holds a metric, cost, latency, URL or model id value, only its TODO-OWNER token
    And no eval number, cost, latency, demo URL or concrete model id appears anywhere outside the slots
    And the architecture text describes model routing per role (router, classifier, answer, embeddings, each from env) without naming model ids

  Scenario: Factual claims match the built code
    When the story writes the template's guardrail values and factual claims
    Then each is verified against the built code and infra/runtime-env.yaml: 500 characters, 16 KiB body, 5 per minute and 50 per day per IP, $1.00 daily cap, 60 s turn timeout, max_tokens 100/400/700/300, max-instances=1, "21 basic and special moves", "a few hundred section chunks" (against data/index/chunks.json) and "at most three model calls"
    And where the code differs, the README states the code's value
    And every correction is listed in the PR description

  Scenario: Sentences carrying required facts are not dropped
    When wording is tightened
    Then section 3 still names dice, outcome text and citation validation as deterministic code and says why
    And section 6 still states every guardrail with its value and the disclosure that messages are sent to Langfuse while IPs are never traced
    And section 8 still lists every handoff 3 out-of-scope item plus the multilingual nice-to-have

  Scenario: Reproduction commands and no secrets
    When README.md is written
    Then it contains "make eval" and "make compare"
    And neither README.md nor docs/development.md contains a secret, key or project id ("GCP_PROJECT" stays a "<id>" placeholder)
```

## Technical Notes

- Implements: *README Content* (the full template and its four rules), *ADR Reference Tokens* (all 15 tokens), *Development Guide (`docs/development.md`)*, and *Assumptions & Decisions* D1, D2, D3, D4, D7, D8, D9, D12, D13. *Feature Name & Description* → the no-fabrication rule and the "fully written / owner-gated" split are binding.
- Placeholder convention (D1) is exact: tokens are literally `TODO-OWNER(<slot-id>)` for the five slot ids in *Placeholder Slots and Owner Fill Procedure*; each slot keeps both its HTML comment and its visible token(s). The `{{adr:<key>}}` family (D2) is a separate, template-only family: all resolved, none committed. Do not use the owner token for ADR numbers, and do not resolve owner slots. The tuning-round ADR number is not filled here; it enters only via `eval-comparison`.
- D7: the code wins over the spec's numbers; eval/cost table row labels stay identical to spec 010's row labels (recall uses the fixed `k`).
- *Validation Rules* rows are the acceptance bar (enforced by story 002's tests, plus the *(review)* rows: Facts, No fabrication).
- *Authorization & Security*: Langfuse/IP disclosure, no secrets, `GCP_PROJECT` stays `<id>`.
- *Impact on Existing Code*: touches only `README.md` (modify, deliberate restructure) and `docs/development.md` (create). Do not change `ATTRIBUTION.md`, `LICENSE`, `docs/decisions.md`, `docs/architecture.md`, `docs/deploy.md`, `evals/README.md`, `Makefile` or `backend/tests/test_repository_compliance.py`. No `docs/media/demo.gif` (owner, D10).
- Read-only inputs: `docs/decisions.md` (ADR numbers), `infra/runtime-env.yaml`, `data/index/chunks.json`, built code under `backend/`, `Makefile`.

## Tests

No spec test case belongs to this slice (all of *Testing* is in story 002). Verify per *Suggested Story Breakdown* item 1:
- `grep -c "{{" README.md` prints 0.
- `grep -c "TODO-OWNER" README.md` prints more than 0.
- Spec 001's `test_readme_has_attribution_section` is green.

**Priority:** Critical
**Dependencies:** None (requires specs 001–011 built)
