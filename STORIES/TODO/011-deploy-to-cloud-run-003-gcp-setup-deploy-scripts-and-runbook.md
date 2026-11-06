# 011-deploy-to-cloud-run-003-gcp-setup-deploy-scripts-and-runbook

**Spec:** STORIES/SPECS/011-deploy-to-cloud-run.md

**As a** project owner
**I want** idempotent GCP setup and deploy scripts, committed non-secret runtime config, and a runbook
**So that** I can create the GCP resources once and deploy a single-instance Cloud Run service with secrets from Secret Manager and spec 008's guardrails effective, using only `make` targets

## Acceptance Criteria

```gherkin
Feature: GCP setup and deploy scripts, runtime config, runbook

  Scenario: One-time setup is idempotent
    Given GCP_PROJECT is a valid project id and my local gcloud credentials
    When I run make gcp-setup GCP_PROJECT=<id> (once or repeatedly)
    Then the Run, Artifact Registry and Secret Manager APIs are enabled
    And the dw-companion Docker repository exists in GCP_REGION (default europe-west1), with infra/ar-cleanup-policy.json always applied
    And the dw-companion-run service account exists
    And each of the three secret ids from D7 exists and is bound to dw-companion-run with roles/secretmanager.secretAccessor only
    And Docker is configured for <region>-docker.pkg.dev
    And steps already done are skipped, every gcloud call passes --project, and "setup: done" is printed with the next command

  Scenario: Secret values are entered safely
    Given a secret has no enabled version
    When setup.sh runs
    Then it prompts "Value for <id> (input hidden): " with hidden input and adds the value from stdin
    And the value is never echoed
    Given the entered value is empty
    Then setup.sh errors and exits 1 without re-prompting

  Scenario Outline: Script input validation
    Given <input> is <bad value>
    When I run <script>
    Then it prints an error prefixed with the script name to stderr and exits 1

    Examples:
      | script               | input           | bad value                                            |
      | setup.sh / deploy.sh | GCP_PROJECT     | missing or not matching ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ |
      | setup.sh / deploy.sh | GCP_REGION      | non-empty and not matching ^[a-z]+-[a-z]+[0-9]+$       |
      | deploy.sh            | MIN_INSTANCES   | non-empty and not exactly 0 or 1                     |
      | deploy.sh            | working tree    | git status --porcelain not empty                     |
      | deploy.sh            | index           | data/index/manifest.json missing                     |

  Scenario: Deploy builds, pushes, deploys and smoke-checks
    Given valid inputs and a clean working tree
    When I run make deploy GCP_PROJECT=<id>
    Then the image is built for linux/amd64 and pushed, tagged with git rev-parse --short=12 HEAD
    And gcloud run deploy runs with exactly the spec's flags: max-instances 1, min-instances $MIN_INSTANCES (default 1), allow-unauthenticated, the dw-companion-run service account, infra/runtime-env.yaml as env-vars file, and the three secrets as :latest Secret Manager references
    And it prints "deploy: live at <url> (image <tag>)" and runs infra/smoke.sh against the URL
    And a smoke failure exits 1 and prints the rollback command from docs/deploy.md

  Scenario: Opting out of the always-on instance warns about the daily cap
    Given MIN_INSTANCES=0
    When I run make deploy
    Then it prints "deploy: warning: MIN_INSTANCES=0 lets the daily spend cap reset on every cold start (see docs/deploy.md)"

  Scenario: Committed runtime config is valid and secret-free
    Given infra/runtime-env.yaml
    Then every non-blank, non-comment line matches ^[A-Z][A-Z0-9_]*: "[^"\\]*"$ with unique keys that all exist in .env.example
    And it contains none of OPENROUTER_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, SITE_DIR
    And CHAT_TRUSTED_PROXY_HOPS is "1"
    And MODEL_EMBEDDINGS equals data/index/manifest.json's embedding_model (skipped with the spec's reason when the manifest is absent)

  Scenario: Documentation exists
    Then docs/deploy.md has the seven sections in the spec's order, stating that no script performs the owner account steps
    And docs/decisions.md has a new ADR numbered highest existing ADR-NNN + 1
    And README.md has "### Running the container and deploying" under "## Development", with the docker run command including -e SITE_DIR=/app/site/dist and the note on why it is needed
    And infra/.gitkeep is deleted
```

## Technical Notes

Implements:
- Assumptions & Decisions → D1 (min/max instances, `MIN_INSTANCES=0` override), D5, D6, D7 (names, region, tag, secret ids), D8, D9, D10, D11, D13 (documented only, never automated), D14 (`Live URL:` line placeholder), D15, D17 (ADR number).
- Configuration → Environment variables `GCP_PROJECT`, `GCP_REGION`, `MIN_INSTANCES` rows; `infra/runtime-env.yaml` (exact content); `infra/ar-cleanup-policy.json` (exact content); `Makefile` block: the `export GCP_PROJECT GCP_REGION MIN_INSTANCES` line and the `gcp-setup`/`deploy` targets, completing the block exactly as in the spec (story 002 added `image`/`smoke`).
- Infra Scripts → `infra/setup.sh` and `infra/deploy.sh` sections (plus the common script rules).
- Validation Rules → `deploy.sh`/`setup.sh` rows (`GCP_PROJECT`, `GCP_REGION`, `MIN_INSTANCES`, working tree, index, secret value prompt) and the `infra/runtime-env.yaml` row.
- Authorization & Security → secrets handling, least-privilege service account, privacy note on Cloud Run request logs.
- Documentation → `docs/deploy.md` (sections 1–7), the ADR (must state both handoff discrepancies D1 and D2, the idle-cost owner review item, and that budget guards are owner actions), the README subsection. The README docker run command must be exactly `docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local`, with the one-line note from the spec.
- Impact on Existing Code → rows for `infra/setup.sh`, `infra/deploy.sh` (both executable), `infra/runtime-env.yaml`, `infra/ar-cleanup-policy.json`, `Makefile`, `infra/.gitkeep` (delete), `backend/tests/test_deploy_config.py` (add cases), `docs/deploy.md`, `docs/decisions.md`, `README.md` (`## Attribution` untouched).

Files: `infra/setup.sh` (new), `infra/deploy.sh` (new), `infra/runtime-env.yaml` (new), `infra/ar-cleanup-policy.json` (new), `Makefile` (modify, additive), `infra/.gitkeep` (delete), `backend/tests/test_deploy_config.py` (modify, additive), `docs/deploy.md` (new), `docs/decisions.md` (modify, additive), `README.md` (modify, additive).

No GCP access is needed to complete this story; verification is offline.

## Tests

From Testing → `test_deploy_config.py`:
- `test_infra_scripts_are_strict_and_executable`
- `test_deploy_pins_single_instance_and_secrets`
- `test_runtime_env_file_is_valid`
- `test_secret_env_vars_documented`
- `test_cleanup_policy_keeps_recent_versions`

Manual: `bash -n infra/setup.sh infra/deploy.sh infra/smoke.sh` exits 0.

**Priority:** High
**Dependencies:** 011-deploy-to-cloud-run-002-container-image-and-ci-smoke.md
