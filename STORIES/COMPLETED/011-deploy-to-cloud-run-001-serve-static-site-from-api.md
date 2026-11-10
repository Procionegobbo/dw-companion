# 011-deploy-to-cloud-run-001-serve-static-site-from-api

**Spec:** STORIES/SPECS/011-deploy-to-cloud-run.md

**As a** visitor to the deployed rules companion
**I want** the rules site and the assistant API to be served from the same origin
**So that** the widget's relative `/api/chat` works with no CORS and no build-time API URL, and one container can serve everything

## Acceptance Criteria

```gherkin
Feature: Opt-in static site serving from create_app (SITE_DIR)

  Scenario: SITE_DIR unset or blank keeps spec 008 behaviour exactly
    Given SITE_DIR is unset, or set to whitespace only
    When ApiSettings is loaded
    Then site_dir is None
    And create_app registers no static mount
    And GET / returns 404 and the body does not contain the site home page
    And every spec 008 test passes unmodified

  Scenario: SITE_DIR is parsed and resolved
    Given SITE_DIR points to a directory containing index.html
    When ApiSettings is loaded
    Then site_dir is that directory resolved to an absolute path

  Scenario: SITE_DIR is invalid
    Given SITE_DIR points to a missing directory, or to an existing directory without index.html
    When create_app builds its settings
    Then a ConfigError is raised containing "SITE_DIR must be a directory containing index.html"

  Scenario: SITE_DIR error is combined with other ApiSettings problems
    Given SITE_DIR is invalid and CHAT_RATE_PER_MINUTE is "0"
    When ApiSettings is loaded
    Then a single ConfigError names both variables

  Scenario: Pages are served
    Given the site is mounted
    When I GET /
    Then I receive 200, text/html, and the home page body
    When I GET a directory path with a trailing slash such as /rules/x/
    Then I receive 200 with that directory's index.html

  Scenario: Slashless directory request redirects
    Given the site is mounted and /rules/x/index.html exists
    When I GET /rules/x without following redirects
    Then I receive 307 with a Location ending in /rules/x/

  Scenario: Unknown paths serve the site's 404 page
    Given the site is mounted
    When I GET /nope/ or an unknown API path such as /api/nope
    Then I receive 404 with the body of SITE_DIR/404.html

  Scenario: HEAD behaves like GET without a body
    Given the site is mounted
    When I send HEAD to a static path
    Then the response matches GET for that path without a body

  Scenario: Other methods on static paths are rejected
    Given the site is mounted
    When I POST /
    Then I receive 405

  Scenario: Path traversal never escapes SITE_DIR
    Given the site is mounted and a file exists outside SITE_DIR
    When I GET /../secret.txt or /%2e%2e/secret.txt
    Then the response is never 200 and never contains that file's content

  Scenario: API routes take precedence over the mount (spec 008 guards unchanged)
    Given the site is mounted
    When I GET /api/health
    Then I receive 200 {"status": "ok"} with Cache-Control: no-store
    When I POST /api/chat with body {}
    Then I receive 422 invalid_request JSON and no LLM request is made
    When I send spec 008's out_of_scope chat turn
    Then it still streams status router, status out_of_scope, then reply

  Scenario: .env.example declares SITE_DIR
    Given the repository .env.example
    Then it ends with the commented, empty SITE_DIR= entry from the spec
```

## Technical Notes

Implements:
- Assumptions & Decisions → D3 (opt-in `StaticFiles(directory=SITE_DIR, html=True)` mounted at `/` after the API routes).
- Configuration → Environment variables, `SITE_DIR` row; `.env.example` append block.
- Data Model → `API_ENV_VARS` (append `"SITE_DIR"`) and `ApiSettings.site_dir`.
- Validation Rules → `ApiSettings` / `SITE_DIR` row (joins the existing combined `ConfigError`).
- Impact on Existing Code → rows for `backend/api/settings.py`, `backend/api/app.py`, `.env.example`, `backend/tests/test_api_settings.py`, `backend/tests/test_api_site.py`.
- Static Site Serving → the whole behaviour table.

Files: `backend/api/settings.py` (modify, additive), `backend/api/app.py` (modify, additive), `.env.example` (modify, additive), `backend/tests/test_api_settings.py` (modify, additive), `backend/tests/test_api_site.py` (new).

Testing → preamble defines the `make_site(tmp_path)` helper and the reuse of spec 008's `api_helpers.make_client` and fakes. No cache, compression or security headers (Future Considerations). Nothing under `site/` changes. Local verification: `npm run build` in `site/`, then start the API as in spec 008 with `SITE_DIR=site/dist` on one port.

## Tests

From Testing → `test_api_settings.py` (additive):
- `test_site_dir_unset_is_none`
- `test_site_dir_parsed_and_resolved`
- `test_site_dir_must_contain_index`

From Testing → `test_api_site.py` (new; every case except `test_chat_still_streams_with_site_mounted` also asserts `FakeLLMClient.requests == []`):
- `test_site_not_mounted_by_default`
- `test_home_served`
- `test_directory_index_served`
- `test_slashless_directory_redirects`
- `test_unknown_path_serves_404_page`
- `test_api_routes_take_precedence`
- `test_chat_still_streams_with_site_mounted`
- `test_path_traversal_blocked`
- `test_post_to_static_path_not_allowed`

**Priority:** Critical
**Dependencies:** None (requires spec 008 to be implemented)
