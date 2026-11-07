# Decisions

ADR-style log of choices and trade-offs; newest at the bottom; entries are never renumbered or
deleted, superseded entries are marked `Superseded by ADR-NNN`.

## ADR-001: Python toolchain: uv, ruff, pytest, single root project

Date: 2026-11-06
Status: Accepted

### Context

The repo needs one Python toolchain shared by `backend/`, `ingestion/` and, later, `evals/`.
Nothing is published to PyPI, and the deployment container copies source directly, so a
build-backend package is unnecessary overhead.

### Decision

A single root `pyproject.toml` as a uv *virtual* project (`[tool.uv] package = false`), with
Python pinned to 3.12 via `.python-version` (`requires-python = ">=3.12"`). Dev-only
dependencies (`ruff`, `pyright[nodejs]`, `pytest`) live in a `dev` dependency group, added with
`uv add --dev` and locked in a committed `uv.lock` (`uv sync --locked` in CI). No runtime
dependencies are added speculatively; FastAPI, LangGraph and friends arrive with the specs that
use them. Ruff (`target-version = "py312"`, rule sets `E, W, F, I, B, UP, SIM, RUF, PT, N`) is
both linter and formatter, excluding `vendor/` and `site/`. Tests live in `backend/tests/`
(including repo-level compliance tests), with `testpaths = ["backend", "ingestion", "evals"]`
so later specs' tests are collected without config changes.

### Consequences

One lockfile and one set of commands (`uv sync --locked`, `ruff format --check`, `ruff check`,
`pytest`) serve every Python package in the repo. Adding a real dependency later is a one-line
`uv add` plus a one-line justification, per the project brief. The trade-off is that `backend`,
`ingestion` and `evals` are not independently versioned or installable — acceptable since none
of them is ever published separately.

## ADR-002: Static type checker: pyright strict

Date: 2026-11-06
Status: Accepted

### Context

The project needs a type checker. The two realistic options were mypy (with its Pydantic
plugin) and pyright.

### Decision

Use **pyright**, installed from PyPI as `pyright[nodejs]` (bundled Node wheel, so Python-only
CI needs no separate Node install), run in `typeCheckingMode = "strict"` over `backend`,
`ingestion` and `evals`. mypy was considered and rejected: it needs the separate
`pydantic-mypy` plugin to type-check Pydantic/FastAPI models correctly, where pyright supports
`dataclass_transform` natively; pyright is also noticeably faster on CI and is the same engine
as Pylance, so editor diagnostics and CI agree.

### Consequences

Strict mode is noisy against untyped third-party libraries such as LangGraph and Langfuse;
these are handled per-import with targeted `# pyright: ignore[...]` comments as they are
introduced, rather than loosening the global mode. CI depends on a Node-capable pyright wheel
rather than a pure-Python tool, which is a non-issue on GitHub-hosted runners.

## ADR-003: Rules source pinned as git submodule

Date: 2026-11-06
Status: Accepted

### Context

The Dungeon World rules text must be pulled from its upstream source rather than hand-copied,
per the project brief, and the exact source revision must be recorded and reproducible.

### Decision

The upstream repository <https://github.com/Sagelt/Dungeon-World> is vendored as a git
submodule at `vendor/dungeon-world/`, added over HTTPS (so CI and anonymous clones work with no
credentials), pinned to commit `e67bd51c09d24518a7f989149b76094fbcc7fecc` — the tip of
`master` as of 2023-02-28 ("Move to entirely CC-BY"), the commit that consolidated upstream
licensing to CC BY and therefore the cleanest licensing baseline. The submodule is vendored in
full, including `layout/`, `character_sheets/` and `resources/`, since submodules cannot be
partial without sparse-checkout complexity; only files under `vendor/dungeon-world/text/` are
ever read, copied or served by this project.

### Consequences

Cloning the repo requires `git submodule update --init` (or `--recurse-submodules`), which is
documented in the README and enforced by a compliance test that fails with that exact
suggestion if the submodule is missing. Updating the rules text later is a deliberate,
reviewable commit-pin bump rather than an implicit upstream change.

## ADR-004: Licensing split: MIT code, CC BY 3.0 text, SRD 5.1 notice

Date: 2026-11-06
Status: Accepted

### Context

The repository mixes original code with adapted third-party rules text under a different
licence, and the upstream `LICENSE` file (read as part of ADR-003) turned out to carry a second,
nested attribution requirement.

### Decision

`LICENSE` at the repo root is the verbatim, unmodified standard MIT License text, with
copyright line `Copyright (c) 2026 Federico Maiorini`; it is never edited to carve out the
rules text, since doing so would break GitHub's licence detection and muddy the standard text.
The "code only" scope of that licence is instead stated in `README.md` and `ATTRIBUTION.md`.
Reading the pinned commit's upstream `LICENSE` showed it also carries a notice that some
material originates from Wizards of the Coast's SRD 5.1 under CC BY 4.0; `ATTRIBUTION.md`
reproduces that notice verbatim, in addition to the CC BY 3.0 credit to Sage LaTorra and Adam
Koebel, as CC BY 4.0 requires carrying that attribution forward.

### Consequences

`ATTRIBUTION.md` is the single place that fully states the licensing split and is checked by
compliance tests so it cannot silently regress. Anyone redistributing this project's code under
MIT must still separately honour CC BY 3.0 and the SRD 5.1 CC BY 4.0 notice for the rules text.

## ADR-005: Frontend placeholder tooling: npm, tsc strict, ESLint

Date: 2026-11-06
Status: Accepted

### Context

The `site/` folder needs a minimal TypeScript toolchain so CI can gate the frontend from day
one, before spec 004 replaces the placeholder with the real Astro application.

### Decision

`site/` uses **npm** (ships with Node, no extra tool to install), **TypeScript in strict mode**
(`tsconfig.json`: `strict: true`, `noUncheckedIndexedAccess: true`, `noEmit: true`, checked via
`tsc --noEmit`), and **ESLint flat config** (`@eslint/js` recommended plus `typescript-eslint`
strict, non-type-checked, to keep lint fast). Node is pinned to **22** via `site/.nvmrc`,
matching the owner's machine and Node's LTS window through 2027-04. A single placeholder
`site/src/index.ts` (`export {};`) exists only so `tsc` has an input to check. No Prettier or
other formatter is configured yet — that choice is deferred to spec 003/004 alongside the
Astro builder. No Astro dependency is added here.

`site/package.json` fixes a **script-name contract for spec 004**: the scripts are named
`"lint": "eslint ."` and `"typecheck": "tsc --noEmit"`. CI (and this project's tooling) calls
scripts by these names only; spec 004 may change what the scripts run (e.g. swap in
`astro check`) and delete the placeholder `index.ts`, but must keep the two names so CI needs
no change across that swap.

### Consequences

`site/` passes `npm ci && npm run lint && npm run typecheck` with zero findings and no Astro or
Prettier dependency present. Spec 004 inherits a working CI gate and a fixed script-name
contract, so introducing Astro is a same-named-script change rather than a CI rewrite.

## ADR-006: CI scope and the no-paid-API rule

Date: 2026-11-06
Status: Accepted

### Context

CI must gate every pull request and push to `main` without ever being able to reach a paid
API, including from a pull request opened by a fork (which GitHub never grants secrets to under
the right trigger, but the workflow itself must not undermine that by defining credentials
another way).

### Decision

A single workflow, `.github/workflows/ci.yml` (`name: CI`), triggers on `pull_request` (all
branches) and on `push` to `main` — never `pull_request_target`, which would run with the base
branch's permissions and secrets against untrusted fork code. Top-level `permissions:
contents: read` and `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`
apply to the whole workflow. No step references `secrets.*` and no job defines a
credential-bearing `env`, so the workflow has nothing to leak and cannot call a paid API even by
mistake. Two parallel jobs run on `ubuntu-latest` with `timeout-minutes: 10`: `python`
(`actions/checkout@v7` with `submodules: true`, `astral-sh/setup-uv@v10` with
`enable-cache: true`, then `uv sync --locked`, `uv run ruff format --check .`,
`uv run ruff check .`, `uv run pyright`, `uv run pytest` as five separately named steps) and
`site` (`actions/checkout@v7` without submodules, `actions/setup-node@v7` with
`node-version-file: site/.nvmrc`, `cache: npm`, `cache-dependency-path: site/package-lock.json`,
then `npm ci`, `npm run lint`, `npm run typecheck`, with `defaults.run.working-directory: site`).
Actions are pinned to the major tags current as of 2026-11-04. Evals get their own, separate,
manually-triggered workflow in spec 009 rather than running here.

### Consequences

Every PR and push to `main` gets fast, read-only, secret-free feedback; a compliance test
(`test_ci_workflows_reference_no_secrets`) fails the suite outright if `.github/workflows/` is
ever missing or stops containing a workflow, so the no-secrets guarantee cannot regress
silently. The trade-off is that any future job needing a real credential (e.g. a staging
deploy) needs its own, explicitly-scoped workflow rather than extending this one.
