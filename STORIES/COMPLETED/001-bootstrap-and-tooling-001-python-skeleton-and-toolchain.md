# 001-bootstrap-and-tooling-001-python-skeleton-and-toolchain

**Spec:** STORIES/SPECS/001-bootstrap-and-tooling.md

**As a** developer of dw-companion
**I want** a single root Python project with uv, ruff, pyright (strict) and pytest, plus the empty hexagonal package layout
**So that** every later spec only adds modules and runs the same install/format/lint/type-check/test commands locally and in CI

## Acceptance Criteria

```gherkin
Feature: Python skeleton and toolchain

  Scenario: Fresh install from the lockfile
    Given a fresh clone of the repository
    When I run "uv sync --locked" from the repo root
    Then it succeeds using Python 3.12 from ".python-version"
    And only the dev group (ruff, pyright[nodejs], pytest) is installed, with no runtime dependencies

  Scenario: The five Python commands pass
    Given the environment is synced
    When I run "uv run ruff format --check .", "uv run ruff check .", "uv run pyright" and "uv run pytest"
    Then each exits 0
    And pyright reports zero warnings and ruff reports zero findings

  Scenario: Layer packages are importable
    Given the empty packages backend.domain, backend.ports, backend.adapters, backend.graph, backend.api and ingestion
    When the test suite imports each one by name with importlib
    Then each import succeeds and the module's __name__ equals the imported name

  Scenario: Dependencies are added by uv, not hand-written
    Given pyproject.toml
    When I inspect the dev dependency group
    Then each entry has the ">=<resolved version>" form written by "uv add --dev"
    And uv.lock is present and committed

  Scenario: Placeholder directories exist
    Given the repository
    Then backend/domain/__init__.py, backend/ports/__init__.py, backend/adapters/__init__.py, backend/graph/__init__.py, backend/api/__init__.py, backend/tests/__init__.py, ingestion/__init__.py, data/normalized/.gitkeep, evals/datasets/.gitkeep, evals/reports/.gitkeep and infra/.gitkeep are tracked in git

  Scenario: .gitignore is extended additively
    Given the existing .gitignore containing ".DS_Store"
    When the story is complete
    Then ".DS_Store" is still present
    And ".env", ".venv/", "__pycache__/", ".pytest_cache/", ".ruff_cache/", "site/node_modules/" and "site/dist/" are appended

  Scenario: Vendored and site code are never linted
    Given the ruff configuration
    Then "vendor" and "site" are excluded via extend-exclude
```

## Technical Notes

Implements:
- Assumptions & Decisions → D1, D2, D3, D4, D5, D6, D16 (no Makefile).
- Configuration → `pyproject.toml` (full block; dev entries via `uv add --dev pytest "pyright[nodejs]" ruff`, never hand-versioned), `.python-version`.
- Impact on Existing Code → rows `.gitignore`, `pyproject.toml`, `uv.lock`, `.python-version`, `backend/__init__.py`, `backend/{domain,ports,adapters,graph,api}/__init__.py`, `backend/tests/__init__.py`, `backend/tests/test_toolchain.py`, `ingestion/__init__.py`, `data/normalized/.gitkeep`, `evals/datasets/.gitkeep`, `evals/reports/.gitkeep`, `infra/.gitkeep`.
- Python Toolchain & Commands → the full command table (the contract shared with CI and the README).
- Testing → the `REPO_ROOT` convention and plain-function style apply here.

Files touched: `.gitignore`, `pyproject.toml`, `uv.lock`, `.python-version`, `backend/**/__init__.py`, `backend/tests/test_toolchain.py`, `ingestion/__init__.py`, `data/normalized/.gitkeep`, `evals/datasets/.gitkeep`, `evals/reports/.gitkeep`, `infra/.gitkeep`.

Out of this slice: submodule, licence/attribution/docs files, `.env.example` (story 002), `site/` (story 003), CI (story 004).

## Tests

`backend/tests/test_toolchain.py`:
- `test_python_runtime_is_at_least_3_12`
- `test_layer_package_is_importable` (parametrized over `backend.domain`, `backend.ports`, `backend.adapters`, `backend.graph`, `backend.api`, `ingestion`)

Manual: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` exit 0.

**Priority:** Critical
**Dependencies:** None
