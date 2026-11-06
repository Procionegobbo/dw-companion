# 011-deploy-to-cloud-run-002-container-image-and-ci-smoke

**Spec:** STORIES/SPECS/011-deploy-to-cloud-run.md

**As a** project owner
**I want** a single container image that serves the rules site and the API, plus a cost-free smoke check that CI runs against it on every PR
**So that** I know the image builds, the real runtime starts, and one origin serves both the site and the API before anything is deployed

## Acceptance Criteria

```gherkin
Feature: Container image, smoke check and CI image job

  Scenario: The image builds from an allow-listed context
    Given the committed data/normalized/ and data/index/
    When I run make image
    Then docker builds dw-companion:local from the multi-stage Dockerfile
    And the build context contains only the allow-listed paths, so .env, .git, vendor/, STORIES/, evals/, backend/tests/ and local build output never enter it

  Scenario: Image contents and runtime constraints
    Given the built image
    Then the runtime stage runs as non-root user app (uid 10001) after its final COPY
    And it sets SITE_DIR=/app/site/dist and copies the site built in the site stage
    And it copies the committed data/normalized/ and data/index/ without re-running ingestion or the index build
    And uvicorn runs create_app as a factory with --workers 1, --no-access-log, proxy headers, on ${PORT:-8080}
    And no COPY/ADD mentions vendor, .env or .git, and no ARG/ENV names OPENROUTER_API_KEY or LANGFUSE_*
    And ARG UV_VERSION is exactly 0.13.5, an exact version, never latest

  Scenario: Smoke check passes against a running container
    Given the image running locally via
      docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local
    When I run make smoke URL=http://127.0.0.1:8080
    Then smoke.sh polls GET /api/health until 200 (up to 30 times, 2 s apart)
    And it prints "smoke: ok <name>" for each of health, home, assistant, move-page, slash-redirect, not-found, chat-rejects-invalid
    And it prints "smoke: all 7 checks passed" and exits 0

  Scenario: Smoke check reports failures
    Given a check's pass condition is not met
    When smoke.sh runs
    Then it prints "smoke: FAIL <name>: <detail>", still runs the remaining checks, and exits 1

  Scenario: Smoke check over https requires an https redirect
    Given BASE_URL starts with https://
    When the slash-redirect check runs
    Then it passes only if the 307 Location also starts with https://

  Scenario: Smoke check makes no paid call
    When smoke.sh runs
    Then its only POST /api/chat sends body {} and expects 422 "invalid_request"

  Scenario: Smoke check rejects a bad BASE_URL
    Given BASE_URL is missing or does not start with http:// or https://
    When I run infra/smoke.sh
    Then it prints "smoke: error: usage: infra/smoke.sh BASE_URL" and exits 2

  Scenario: CI builds and smoke-tests the image without secrets
    Given a pull request
    When the CI image job runs
    Then it builds dw-companion:ci, starts it with placeholder non-credential env values and no Langfuse keys
    And infra/smoke.sh reports all 7 checks passed
    And on failure the job prints docker logs app
    And ci.yml still contains no "secrets." reference and the existing jobs are unchanged
```

## Technical Notes

Implements:
- Assumptions & Decisions → D2 (copy committed data, build only the site in Docker), D4 (uvicorn `--proxy-headers --forwarded-allow-ips '*'`), D12 (CI `image` job), D16 (base images, `UV_VERSION=0.13.5`, non-root `app`).
- Container Image → the exact `Dockerfile` content and its Notes. Preserve the spec's pinned line exactly: `ARG UV_VERSION=0.13.5`.
- Configuration → `.dockerignore` (exact content); `Makefile` block: only the `image` and `smoke` targets (with their `.PHONY` entries). The `export` line and the `gcp-setup`/`deploy` targets belong to story 003.
- Infra Scripts → common rules for all scripts (shebang, `set -euo pipefail`, bash 3.2, `cd "$(dirname "$0")/.."`, `${VAR:-}`, error prefix) and the `infra/smoke.sh BASE_URL` section with its check table.
- Validation Rules → `smoke.sh` / `BASE_URL` row; `Dockerfile` / `ARG UV_VERSION` row.
- CI Image Job → all steps.
- Impact on Existing Code → rows for `Dockerfile`, `.dockerignore`, `infra/smoke.sh` (executable), `Makefile`, `.github/workflows/ci.yml`, `backend/tests/test_deploy_config.py` (new; this story creates it with the cases below and the stage-splitting helper).
- Testing → Manual: the documented local run command must be used exactly as written, including the explicit `-e SITE_DIR=/app/site/dist`, because the empty `SITE_DIR=` in `.env` would otherwise override the image default: `docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local`.

Files: `Dockerfile` (new), `.dockerignore` (new), `infra/smoke.sh` (new, executable), `Makefile` (modify, additive), `.github/workflows/ci.yml` (modify, additive), `backend/tests/test_deploy_config.py` (new).

Prerequisites: spec 009's `Makefile` must exist; spec 007's committed `data/index/` must exist or the image build fails at `COPY` (open risk f).

## Tests

From Testing → `test_deploy_config.py`:
- `test_dockerignore_is_allow_list`
- `test_dockerfile_never_copies_secrets_or_vendor`
- `test_runtime_stage_runs_as_non_root`
- `test_runtime_command_matches_api_constraints`
- `test_runtime_stage_sets_site_dir`
- `test_image_versions_match_toolchain`

CI: the `image` job (CI Image Job) is the image-level test; `infra/smoke.sh` reports all 7 checks passed.

Manual: `make image` succeeds locally; `docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local` then `make smoke URL=http://127.0.0.1:8080` passes.

**Priority:** Critical
**Dependencies:** 011-deploy-to-cloud-run-001-serve-static-site-from-api.md
