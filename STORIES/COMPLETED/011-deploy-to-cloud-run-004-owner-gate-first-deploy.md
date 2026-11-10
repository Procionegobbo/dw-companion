# 011-deploy-to-cloud-run-004-owner-gate-first-deploy

**Spec:** STORIES/SPECS/011-deploy-to-cloud-run.md

> **Owner checklist, not a feature-builder story.** Every step uses the owner's own GCP, OpenRouter and Langfuse accounts; no agent can perform them (D13). Do not hand this file to an implementation agent.

**As a** project owner
**I want** to set up the account-level guards, deploy the service for the first time and verify the guardrails on the live URL
**So that** milestone 10 is met: a public URL where anyone can read the rules and use the assistant, with spend bounded by code and by account-level guards

## Acceptance Criteria

```gherkin
Feature: Owner gate for the first Cloud Run deploy (milestone 10 acceptance)

  Scenario: Cost decision and account guards (Owner Gate steps 1-2)
    Given I have reviewed D1 (idle cost of min-instances=1)
    Then I have decided MIN_INSTANCES
    And the GCP project has billing and a budget alert
    And the production OpenRouter key has a credit limit with auto top-up off
    And a Langfuse cloud project with a key pair exists

  Scenario: Setup and deploy (Owner Gate steps 3-4)
    When I run make gcp-setup GCP_PROJECT=<id> and enter the three secret values
    And I run make deploy GCP_PROJECT=<id>
    Then the smoke check passes against the https:// URL
    And gcloud run services describe shows max-instances=1 and the chosen min-instances
    And the three keys are Secret Manager references in the service config, not plain env values

  Scenario: Browser check (Owner Gate step 5)
    When I open the home page and a rules page
    Then both load
    When I ask "How does Hack and Slash work?" on /assistant/
    Then progress is shown, then an answer whose citation links open /rules/…/ pages on the same host

  Scenario: Rate limit resists X-Forwarded-For spoofing (Owner Gate step 6)
    When I send 6 valid "hello" requests within a minute, each with a different X-Forwarded-For: 198.51.100.<n>
    Then requests 1-5 get 200 and request 6 gets 429 rate_limited

  Scenario: Rate limit is per visitor (Owner Gate step 6)
    Given I am still rate limited
    When I send one request from a different network
    Then it gets 200

  Scenario: Spend cap is effective (Owner Gate step 6)
    Given CHAT_DAILY_BUDGET_USD is set to 0.0001 on the live service
    When I send two requests
    Then the first gets 200 and the second gets 503 budget_exhausted
    And make deploy then restores the committed config

  Scenario: A guardrail check fails
    When any step 6 check fails
    Then I adjust CHAT_TRUSTED_PROXY_HOPS in infra/runtime-env.yaml, redeploy and repeat

  Scenario: Traces and URL (Owner Gate steps 7-8)
    Then Langfuse shows the step 5 and 6 turns with model, tokens and cost under the production session ids
    And docs/deploy.md's "Live URL:" line contains the live https:// URL, committed
```

## Technical Notes

Covers spec sections Owner Gate (steps 1–8) and Success Criteria → Owner verification. Procedures are in `docs/deploy.md` (created by story 003). Related: D1, D13, D14; open risks a (trace export under CPU throttling), b (`X-Forwarded-For` layout), c (counters reset per deploy), d (org policy may block `allUsers`), e (memory).

Files: `docs/deploy.md` (`Live URL:` line only); `infra/runtime-env.yaml` only if a step 6 check requires a `CHAT_TRUSTED_PROXY_HOPS` change.

## Tests

Manual only: Owner Gate steps 1–8 and the five Success Criteria → Owner verification items.

**Priority:** High
**Dependencies:** 011-deploy-to-cloud-run-003-gcp-setup-deploy-scripts-and-runbook.md
