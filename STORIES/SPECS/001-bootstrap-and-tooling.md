# 001 - Bootstrap and tooling

**Status:** spec — ready for story-creator.
**Depends on:** none (first spec).
**Reference:** `HANDOFF_dw-companion.md` sections 1, 2, 4.1, 6.4, 9, 10 (milestone 1), 12.

## Feature Name & Description

**Bootstrap and tooling.** Stand up the empty-but-wired repository skeleton for dw-companion (Dungeon World rules site + AI assistant): Python toolchain, TypeScript lint/typecheck placeholder for `site/`, GitHub Actions CI, the pinned Dungeon World source as a git submodule, and the licensing/attribution files. Every later spec builds on the conventions fixed here, so this spec is the project's first precedent.

**Current state.** The repo contains only `HANDOFF_dw-companion.md`, `.gitignore` (one line: `.DS_Store`), the pipeline scaffolding (`.claude/agents/python-feature-builder.md`, `STORIES/`), and spec drafts. No `pyproject.toml`, no `package.json`, no CI, no submodule, no licence files.

**In scope.** Folder layout (handoff section 9); Python 3.12 + `uv` + `ruff` + `pyright` (strict) + `pytest` with smoke and repository-compliance tests; minimal `site/` TypeScript tooling (npm, `tsc` strict, ESLint) with no Astro; CI on every PR; submodule pinned to a recorded commit; `LICENSE` (MIT), `ATTRIBUTION.md` (complete), `README.md` stub with an Attribution section; stub docs; `.env.example`.

**Out of scope.** The ingestion parser (spec 002), the Astro application and any page (spec 004), any backend logic (specs 005+), evals runner and its workflow (spec 009), Dockerfile and `infra/` content (spec 011), the final README (spec 012).

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Type checker: pyright, `typeCheckingMode = "strict"`**, installed from PyPI as `pyright[nodejs]` (bundled Node wheel, no separate Node install needed for Python CI). | `.claude/agents/python-feature-builder.md` already assumes `uv run pyright`; pyright supports `dataclass_transform` natively (Pydantic/FastAPI models type-check without a plugin, unlike mypy's pydantic plugin); much faster on CI; same engine as Pylance so editor and CI agree. Trade-off accepted: pyright is Node-based and strict mode is noisy with untyped third-party libs (LangGraph, Langfuse) — handled per-import later with targeted `# pyright: ignore[...]` rather than loosening the global mode. |
| D2 | **One root `pyproject.toml`**, uv *virtual* project (`[tool.uv] package = false`), no build backend. Top-level packages `backend`, `ingestion` (and later `evals`) are imported from the repo root via pytest `pythonpath = ["."]` and pyright's default root execution environment. | The handoff layout puts `backend/`, `ingestion/`, `evals/` side by side at root and they share models/tooling; nothing is published to PyPI, and the container (spec 011) copies source. One lockfile, one toolchain. |
| D3 | **Python pinned to 3.12** via `.python-version` (`3.12`), `requires-python = ">=3.12"`. CI tests one version only. | Handoff "3.12+"; the runtime container will use one version, so a matrix adds CI time without signal. uv honours `.python-version` and downloads a managed interpreter. |
| D4 | **Dev dependencies only** (`ruff`, `pyright[nodejs]`, `pytest`) in a `dev` dependency group; **no runtime dependencies** yet. Added with `uv add --dev …` (uv writes `>=` lower bounds at the then-current version); `uv.lock` is committed and CI runs `uv sync --locked`. | Handoff 12: "Prefer boring, well-known libraries. Every new dependency gets one line of justification in the PR description." No speculative deps. FastAPI/LangGraph arrive with the specs that use them. |
| D5 | **Ruff**: `target-version = "py312"`, default line length (88), rule sets `E, W, F, I, B, UP, SIM, RUF, PT, N`; `ruff format` is the formatter. `vendor/` and `site/` excluded. | Common, low-noise set covering bugs, imports, modernisation and pytest style. `vendor/` contains an upstream Python script (`resources/correctformatting.py`) that must never be linted. |
| D6 | **Tests live in `backend/tests/`** (package with `__init__.py`), including repo-level compliance tests (attribution, licence, submodule, `.env.example`). `testpaths = ["backend", "ingestion", "evals"]` so later specs' tests are collected without config changes. | Handoff 4.1/9 names `backend/tests/` as the only test root; compliance checks make "ATTRIBUTION.md complete" binary and guard it against regressions. |
| D7 | **Source pinned as a git submodule** at `vendor/dungeon-world/`, URL `https://github.com/Sagelt/Dungeon-World` (HTTPS so CI and anonymous clones work), commit **`e67bd51c09d24518a7f989149b76094fbcc7fecc`** (tip of `master`, 2023-02-28, "Move to entirely CC-BY"; verified 2026-11-04 with `git ls-remote`). | Handoff 2 [decided]: "Pull the source as a git submodule or a pinned download (record the commit hash). Do not hand-copy text." This commit is the one that consolidated upstream licensing to CC BY, so it is the cleanest licensing baseline. |
| D8 | **Upstream `LICENSE` also carries an SRD 5.1 notice** (material from Wizards of the Coast's SRD 5.1 under CC BY 4.0). `ATTRIBUTION.md` reproduces that notice verbatim in addition to the CC BY 3.0 credit. | Discovered by reading the pinned commit's `LICENSE`. CC BY 4.0 requires carrying that attribution forward; handoff 2 says "read the repo's LICENSE file and follow it". The handoff's credit list (Sage LaTorra, Adam Koebel, CC BY 3.0) stays binding and unchanged; this is an addition, not a reinterpretation. |
| D9 | **`LICENSE` is the verbatim MIT text**, `Copyright (c) 2026 Federico Maiorini`. The "code only" scope is stated in `README.md` and `ATTRIBUTION.md`, not by editing `LICENSE`. | Editing the licence body breaks GitHub's licence detection and muddies the standard text. Copyright holder taken from the repo's git author. |
| D10 | **The submodule is the whole upstream repo** (it includes `layout/`, `character_sheets/`, `resources/`). Nothing outside `vendor/dungeon-world/text/` is ever read, copied or served. | Submodules cannot be partial without sparse-checkout complexity. Handoff 2 forbids using art/trade dress; the rule is "never consume", stated in `ATTRIBUTION.md` and enforced in later specs (002 reads only `text/`, 011 must not copy `vendor/` into the image beyond ingestion). |
| D11 | **`site/` tooling: npm, TypeScript strict `tsc --noEmit`, ESLint flat config (`@eslint/js` recommended + `typescript-eslint` strict, non-type-checked), Node 22** (`site/.nvmrc`). A single placeholder `site/src/index.ts` (`export {};`) exists only so `tsc` has an input. No Prettier yet. | Draft limits TS tooling to what makes an empty `site/` pass lint/typecheck. npm ships with Node (no extra tool); Node 22 matches the owner's machine and is LTS until 2027-04. Formatter choice is deferred to spec 003/004 with the Astro builder. **Contract for spec 004:** the `npm run lint` and `npm run typecheck` script names are what CI calls; spec 004 may change their implementation (e.g. `astro check`) and delete the placeholder, but keeps the names. |
| D12 | **CI: one workflow `.github/workflows/ci.yml`** with two parallel jobs, `python` and `site`, triggered on `pull_request` and on `push` to `main`. `permissions: contents: read`, no `secrets.*` and no workflow `env` with credentials, so no paid API can be reached. Uses `pull_request` (never `pull_request_target`). | Handoff 6.4. Push-to-main runs give the default branch a status. Evals get their own manual workflow in spec 009. |
| D13 | **GitHub Actions pinned to major tags current on 2026-11-04**: `actions/checkout@v7`, `astral-sh/setup-uv@v10`, `actions/setup-node@v7` (verified via `gh api repos/<owner>/<repo>/releases/latest`). | Major tags get security fixes without churn; SHA pinning is a possible later hardening (see Future Considerations). |
| D14 | **`.env.example` lists only the four model-routing variables** from handoff 4.2 (`MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER`, `MODEL_EMBEDDINGS`) with empty values, plus a header stating the convention. No API key placeholders yet. | Draft: "do not invent values, just note the pattern". Provider keys depend on spec 007's provider decision (OpenRouter plus an embeddings provider still to be resolved), so 007 adds them. |
| D15 | **ADR format** in `docs/decisions.md`: `## ADR-NNN: <title>` with `Date`, `Status`, `Context`, `Decision`, `Consequences`. Numbered sequentially; never renumbered. | Handoff calls it "ADR-style"; this is the minimal Nygard format. |
| D16 | **No `Makefile`** in this spec. | Not requested; the CI commands are documented in the README stub. `make eval` arrives with spec 009 (see Future Considerations). |

**Open risk:** none for existing code (nothing exists). The one forward risk is D11's placeholder `tsconfig`/ESLint config being replaced by spec 004; the script-name contract above keeps CI stable across that change.

## Architecture / Design Overview

This spec adds no runtime architecture. It fixes the layout from handoff section 9 and the hexagonal package boundaries from section 4.1 as importable, empty Python packages, so later specs only add modules.

```
repo root
├── pyproject.toml / uv.lock / .python-version   ← one Python toolchain for backend, ingestion, evals
├── backend/{domain,ports,adapters,graph,api}/   ← empty packages (hexagonal layers)
├── backend/tests/                               ← pytest root: smoke + repo-compliance tests
├── ingestion/                                   ← empty package (spec 002)
├── vendor/dungeon-world/  (submodule @ e67bd51)  ← read-only CC BY 3.0 source
├── site/  (package.json, tsconfig, eslint)      ← TS placeholder; Astro in spec 004
└── .github/workflows/ci.yml
        ├── job python: uv sync --locked → ruff format --check → ruff check → pyright → pytest
        └── job site:   npm ci → npm run lint → npm run typecheck
```

CI checks out submodules in the `python` job because the compliance test verifies the vendored source and spec 002's ingestion tests will need it. The `site` job does not.

## Configuration

**Environment variables** (`.env.example`, new — exact content):

```dotenv
# dw-companion environment variables.
# Copy to .env for local development (.env is git-ignored). Never commit real values.
# Every variable the code reads must be listed here, with an empty value and a comment
# naming the spec that introduced it. Secrets in deployment come from Secret Manager (spec 011).

# Model routing (handoff 4.2) — consumed from spec 007. Model names only, never hardcoded.
MODEL_ROUTER=
MODEL_CLASSIFIER=
MODEL_ANSWER=
MODEL_EMBEDDINGS=
```

No code reads these yet.

**`pyproject.toml`** (new) — required contents. The unversioned `dev` list below is a placeholder for the form `uv add --dev` writes (each entry becomes `"<name>>=<resolved version>"`); do not hand-write versions (D4). `ingestion/` and `evals/` both exist on disk after this spec (`ingestion/__init__.py`, `evals/datasets/.gitkeep`); pyright and pytest silently skip included directories that contain no Python files or tests, so listing them now produces no warning and later specs (002, 009) need no config change.

```toml
[project]
name = "dw-companion"
version = "0.1.0"
description = "Dungeon World rules site and AI assistant (unofficial)."
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
# written by `uv add --dev pytest "pyright[nodejs]" ruff`, which appends ">=<resolved version>" to each
dev = ["pytest", "pyright[nodejs]", "ruff"]

[tool.uv]
package = false

[tool.ruff]
target-version = "py312"
extend-exclude = ["vendor", "site"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "SIM", "RUF", "PT", "N"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
include = ["backend", "ingestion", "evals"]
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
testpaths = ["backend", "ingestion", "evals"]
pythonpath = ["."]
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
```

**`site/tsconfig.json`** (new): `compilerOptions` = `strict: true`, `noUncheckedIndexedAccess: true`, `noEmit: true`, `target: "ES2022"`, `module: "ESNext"`, `moduleResolution: "Bundler"`, `skipLibCheck: true`; `include: ["src"]`.

**`site/package.json`** (new): `"name": "dw-companion-site"`, `"private": true`, `"type": "module"`, `"engines": { "node": ">=22" }`, scripts `"lint": "eslint ."` and `"typecheck": "tsc --noEmit"`; devDependencies `typescript`, `eslint`, `@eslint/js`, `typescript-eslint` added with `npm install --save-dev` (caret ranges); `site/package-lock.json` committed.

**`site/eslint.config.js`** (new): flat config exporting `defineConfig(js.configs.recommended, tseslint.configs.strict, { ignores: ["dist/"] })`, with `defineConfig` from `eslint/config`, `js` from `@eslint/js`, `tseslint` from `typescript-eslint` (`node_modules/` is ignored by ESLint by default).

**`site/.nvmrc`** (new): `22`.

**`.python-version`** (new): `3.12`.

## Data Model

Not applicable — no persisted entities. (Normalized rulebook shapes are defined in spec 002.)

## Impact on Existing Code

The only existing file touched is `.gitignore`. Everything else is new. `.gitkeep` files keep otherwise-empty directories in git. Paths under `vendor/dungeon-world/` mentioned elsewhere in this spec (`LICENSE`, `text/`, `layout/`, `character_sheets/`, `resources/correctformatting.py`) are upstream content that appears when the submodule is added; they were verified in the upstream repository on 2026-11-04 via `gh api repos/Sagelt/Dungeon-World/contents`.

| Path | Action | Notes |
|------|--------|-------|
| `.gitignore` | modify — **additive** | Keep `.DS_Store`; append `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `site/node_modules/`, `site/dist/`. No existing behaviour changes. |
| `.gitmodules` (new) | create | Created by `git submodule add`; one entry, path `vendor/dungeon-world`, URL per D7. |
| `vendor/dungeon-world` (new) | create | Submodule gitlink at `e67bd51c09d24518a7f989149b76094fbcc7fecc`. |
| `pyproject.toml` (new) | create | See *Configuration*. |
| `uv.lock` (new) | create | Generated by uv, committed. |
| `.python-version` (new) | create | `3.12`. |
| `.env.example` (new) | create | See *Configuration*. |
| `LICENSE` (new) | create | Verbatim MIT, D9. |
| `ATTRIBUTION.md` (new) | create | Exact text in *Attribution & Licensing Files*. |
| `README.md` (new) | create | Stub, exact text in *Attribution & Licensing Files*. |
| `docs/decisions.md` (new) | create | ADR log, see *Documentation Stubs*. |
| `docs/source-notes.md` (new) | create | Stub. |
| `docs/architecture.md` (new) | create | Stub. |
| `backend/__init__.py` (new) | create | Empty. |
| `backend/domain/__init__.py` (new) | create | Empty. |
| `backend/ports/__init__.py` (new) | create | Empty. |
| `backend/adapters/__init__.py` (new) | create | Empty. |
| `backend/graph/__init__.py` (new) | create | Empty. |
| `backend/api/__init__.py` (new) | create | Empty. |
| `backend/tests/__init__.py` (new) | create | Empty. |
| `backend/tests/test_toolchain.py` (new) | create | See *Testing*. |
| `backend/tests/test_repository_compliance.py` (new) | create | See *Testing*. |
| `ingestion/__init__.py` (new) | create | Empty. |
| `data/normalized/.gitkeep` (new) | create | Placeholder. |
| `evals/datasets/.gitkeep` (new) | create | Placeholder. |
| `evals/reports/.gitkeep` (new) | create | Placeholder. |
| `infra/.gitkeep` (new) | create | Placeholder. |
| `site/package.json` (new) | create | See *Configuration*. |
| `site/package-lock.json` (new) | create | Generated by npm, committed. |
| `site/tsconfig.json` (new) | create | See *Configuration*. |
| `site/eslint.config.js` (new) | create | See *Configuration*. |
| `site/.nvmrc` (new) | create | `22`. |
| `site/src/index.ts` (new) | create | `// Placeholder so tsc has an input; replaced by the Astro app in spec 004.` followed by `export {};` |
| `.github/workflows/ci.yml` (new) | create | See *CI Workflow*. |

## Python Toolchain & Commands

Every Python command runs from the repo root through uv. These exact commands are the contract shared by CI, the README and `python-feature-builder`:

| Purpose | Command |
|---------|---------|
| Install | `uv sync --locked` |
| Format check | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Type check | `uv run pyright` |
| Tests | `uv run pytest` |
| Auto-fix locally | `uv run ruff format . && uv run ruff check --fix .` |

All of them must pass on a fresh clone (`git clone --recurse-submodules`) with zero warnings from pyright and zero ruff findings.

## Site Toolchain & Commands

Run from `site/`: `npm ci`, `npm run lint`, `npm run typecheck`. Both must pass with no findings. See D11 for the script-name contract with spec 004.

## CI Workflow

`.github/workflows/ci.yml`, `name: CI`:

- `on: pull_request` (all branches) and `push` to `main`.
- Top-level `permissions: contents: read`; `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`.
- No `secrets.*` references and no credential-bearing `env` anywhere in the file.
- **Job `python`** (`runs-on: ubuntu-latest`, `timeout-minutes: 10`), steps in order: `actions/checkout@v7` with `submodules: true`; `astral-sh/setup-uv@v10` with `enable-cache: true`; then the five commands from *Python Toolchain & Commands* (install, format check, lint, type check, tests), each as its own named step so failures are attributable.
- **Job `site`** (`runs-on: ubuntu-latest`, `timeout-minutes: 10`, `defaults.run.working-directory: site`): `actions/checkout@v7` (no submodules); `actions/setup-node@v7` with `node-version-file: site/.nvmrc`, `cache: npm`, `cache-dependency-path: site/package-lock.json`; steps `npm ci`, `npm run lint`, `npm run typecheck`.

## Attribution & Licensing Files

**`ATTRIBUTION.md`** — exact content:

```markdown
# Attribution

dw-companion is an **unofficial** fan project. It is not affiliated with, sponsored by, or
endorsed by Sage LaTorra, Adam Koebel, or any publisher of Dungeon World.

## Dungeon World rules text

The rules text used by this project comes from **Dungeon World** by **Sage LaTorra** and
**Adam Koebel**, published at <https://github.com/Sagelt/Dungeon-World> and licensed under the
[Creative Commons Attribution 3.0 Unported License (CC BY 3.0)](https://creativecommons.org/licenses/by/3.0/).

The text has been **adapted**: it is parsed from the source XML and reformatted into
structured data, web pages and search chunks. Wording may differ in formatting, structure and
markup from the original. The source is included as a git submodule at
`vendor/dungeon-world/`, pinned to commit `e67bd51c09d24518a7f989149b76094fbcc7fecc`; it is
never hand-copied.

The upstream licence also carries this notice, reproduced as required:

> This work includes material taken from the System Reference Document 5.1 ("SRD 5.1") by
> Wizards of the Coast LLC and available at
> https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 is licensed under
> the Creative Commons Attribution 4.0 International License available at
> https://creativecommons.org/licenses/by/4.0/legalcode.

No art, logos or trade dress from the commercial Dungeon World book are used. Only the text
files under `vendor/dungeon-world/text/` are read; nothing else in the submodule is copied
or served.

## Code

All original source code in this repository is licensed under the MIT License — see
[`LICENSE`](LICENSE). The MIT License covers the code only; the rules text remains under
CC BY 3.0 as described above.
```

**`README.md`** — stub, exact content (spec 012 rewrites everything above *Attribution* and polishes the rest):

```markdown
# dw-companion

An unofficial Dungeon World rules site with an AI assistant for players and GMs at the table.

> Status: under construction.

## Development

Requirements: [uv](https://docs.astral.sh/uv/), Node 22, and a clone with submodules
(`git clone --recurse-submodules`, or `git submodule update --init` in an existing clone).

Python (from the repo root):

    uv sync
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright
    uv run pytest

Site (from `site/`):

    npm ci
    npm run lint
    npm run typecheck

Copy `.env.example` to `.env` for local configuration. Design decisions are logged in
[`docs/decisions.md`](docs/decisions.md).

## Attribution

This project uses the text of **Dungeon World** by Sage LaTorra and Adam Koebel, from
<https://github.com/Sagelt/Dungeon-World>, licensed under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The text has been adapted (parsed
and reformatted). This project is **unofficial** and not endorsed by the authors. See
[`ATTRIBUTION.md`](ATTRIBUTION.md) for full details.

## License

Code: [MIT](LICENSE). Rules text: CC BY 3.0, see [`ATTRIBUTION.md`](ATTRIBUTION.md).
```

**`LICENSE`** — standard MIT License text (as at <https://opensource.org/license/mit>), first line `MIT License`, copyright line `Copyright (c) 2026 Federico Maiorini`.

## Documentation Stubs

**`docs/decisions.md`**: title `# Decisions`, a one-paragraph intro ("ADR-style log of choices and trade-offs; newest at the bottom; entries are never renumbered or deleted, superseded entries are marked `Superseded by ADR-NNN`"), then these entries in D15 format, dated the implementation date, `Status: Accepted`:

| ADR | Title | Content source |
|-----|-------|----------------|
| ADR-001 | Python toolchain: uv, ruff, pytest, single root project | D2, D3, D4, D5 |
| ADR-002 | Static type checker: pyright strict | D1 (state the mypy alternative and why it lost) |
| ADR-003 | Rules source pinned as git submodule | D7, D10 — must include the full commit hash `e67bd51c09d24518a7f989149b76094fbcc7fecc` and the upstream URL |
| ADR-004 | Licensing split: MIT code, CC BY 3.0 text, SRD 5.1 notice | D8, D9 |
| ADR-005 | Frontend placeholder tooling: npm, tsc strict, ESLint | D11 incl. the script-name contract |
| ADR-006 | CI scope and the no-paid-API rule | D12, D13 |

**`docs/source-notes.md`**: `# Source notes` plus one line: "Describes the actual structure of the Dungeon World XML in `vendor/dungeon-world/text/`. Written in spec 002 before the parser."

**`docs/architecture.md`**: `# Architecture` plus one line: "Diagram and node descriptions are added as the graph is built (specs 006–008). Until then see section 4 of the project brief."

## Validation Rules

No runtime input exists in this spec. The repository rules below are enforced by tests (see *Testing*):

| Subject | Rule |
|---------|------|
| `.env.example` | Every non-blank, non-comment line matches `^[A-Z][A-Z0-9_]*=$` (key with empty value). Keys are unique. |
| `ATTRIBUTION.md` | Contains `Sage LaTorra`, `Adam Koebel`, `https://github.com/Sagelt/Dungeon-World`, `https://creativecommons.org/licenses/by/3.0/`, `unofficial`, `adapted`, `SRD 5.1`, `e67bd51c09d24518a7f989149b76094fbcc7fecc`. |
| `README.md` | Has a line exactly `## Attribution`; that section links `ATTRIBUTION.md` and contains `unofficial`. |
| `LICENSE` | First line is `MIT License`. |
| Submodule | `vendor/dungeon-world/LICENSE` exists and contains `Creative Commons Attribution 3.0`. |
| CI | `.github/workflows/*.yml` contain no `secrets.` reference. |

## Authorization & Security

No users, endpoints or permissions exist yet. Security-relevant choices:

- CI has read-only `contents` permission, references no secrets, and runs on `pull_request` (fork PRs get no secrets by design), so no paid API can be called from CI (handoff 6.4).
- `.env` is git-ignored; `.env.example` holds keys only, enforced by test.
- The submodule uses a public HTTPS URL; no credentials are needed to clone it.

## Testing

pytest, files in `backend/tests/`, plain functions, no fixtures beyond a module-level `REPO_ROOT = Path(__file__).resolve().parents[2]`. All tests are offline and deterministic.

**`backend/tests/test_toolchain.py`**
- `test_python_runtime_is_at_least_3_12` — `sys.version_info >= (3, 12)`.
- `test_layer_package_is_importable` — parametrized over `backend.domain`, `backend.ports`, `backend.adapters`, `backend.graph`, `backend.api`, `ingestion`; `importlib.import_module` succeeds and returns a module whose `__name__` equals the parameter.

**`backend/tests/test_repository_compliance.py`**
- `test_attribution_credits_authors_source_and_license` — the author, repo URL and CC BY 3.0 URL strings from *Validation Rules* are present.
- `test_attribution_states_adaptation_and_unofficial_status` — `adapted` and `unofficial` present.
- `test_attribution_reproduces_srd_notice` — `SRD 5.1` and `https://creativecommons.org/licenses/by/4.0/legalcode` present.
- `test_attribution_records_pinned_commit` — the full commit hash is present.
- `test_license_is_mit` — first line of `LICENSE` is `MIT License`.
- `test_readme_has_attribution_section` — `## Attribution` heading present; the text between it and the next `## ` heading contains `ATTRIBUTION.md` and `unofficial`.
- `test_vendored_source_is_checked_out` — `vendor/dungeon-world/LICENSE` exists and contains `Creative Commons Attribution 3.0` (fails with a message suggesting `git submodule update --init` if missing).
- `test_env_example_declares_keys_without_values` — every non-blank, non-comment line matches the pattern in *Validation Rules*, and keys are unique.
- `test_ci_workflows_reference_no_secrets` (written in story 4, together with the workflow) — asserts `.github/workflows/` exists and contains at least one `*.yml` file (so the test cannot pass vacuously; it fails if the directory is missing or empty), then that no such file contains `secrets.`.

**Manual / CI verification (not pytest):** `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `npm run lint`, `npm run typecheck` exit 0; deliberately introducing a type error in `site/src/index.ts` (e.g. `const n: number = "x";`) makes `npm run typecheck` fail — check once, then revert.

## Suggested Story Breakdown

1. **Python skeleton and toolchain** — `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore` additions, all `backend/`/`ingestion/` packages, `.gitkeep` placeholders, `test_toolchain.py`. Verifiable: the five Python commands pass locally. No dependencies.
2. **Source submodule, licensing and docs** — submodule at the pinned commit, `LICENSE`, `ATTRIBUTION.md`, `README.md` stub, `docs/*.md` with ADR-001…004, `.env.example`, `test_repository_compliance.py` with every compliance test except `test_ci_workflows_reference_no_secrets`. Depends on 1.
3. **Site TypeScript placeholder tooling** — everything under `site/`; append ADR-005. Independent of 1–2 (but appends to `docs/decisions.md`, so run after 2). Note: this story touches `site/`, which `python-feature-builder` handles only when a story explicitly requires it — this one does.
4. **CI workflow** — `.github/workflows/ci.yml`; add `test_ci_workflows_reference_no_secrets` to `test_repository_compliance.py`; append ADR-006; open a PR and confirm both jobs green. Depends on 1–3.

## Success Criteria

- [ ] All tests listed in *Testing* exist and pass with `uv run pytest`.
- [ ] `uv run ruff format --check .`, `uv run ruff check .` and `uv run pyright` exit 0 on a fresh `--recurse-submodules` clone.
- [ ] `npm ci && npm run lint && npm run typecheck` in `site/` exit 0.
- [ ] `git submodule status` shows `vendor/dungeon-world` at `e67bd51c09d24518a7f989149b76094fbcc7fecc`.
- [ ] `ATTRIBUTION.md`, `README.md` and `LICENSE` match *Attribution & Licensing Files*.
- [ ] `docs/decisions.md` contains ADR-001 through ADR-006; `docs/source-notes.md` and `docs/architecture.md` exist.
- [ ] These paths are tracked in git: `backend/domain/__init__.py`, `backend/ports/__init__.py`, `backend/adapters/__init__.py`, `backend/graph/__init__.py`, `backend/api/__init__.py`, `backend/tests/__init__.py`, `ingestion/__init__.py`, `data/normalized/.gitkeep`, `evals/datasets/.gitkeep`, `evals/reports/.gitkeep`, `infra/.gitkeep`, `site/package.json`, `docs/decisions.md`, `.github/workflows/ci.yml`, `.gitmodules`.
- [ ] A pull request shows both CI jobs (`python`, `site`) green, and `ci.yml` references no secrets.

## Future Considerations

- `pytest-socket` with `--disable-socket` in `addopts` to make "no network in tests" (and therefore no paid API calls) a hard guarantee rather than a convention — worth adding once spec 006/007 introduce network-capable dependencies.
- A root `Makefile` (`make check`, later `make eval`) mirroring CI commands; spec 009 needs `make eval` anyway.
- Pin GitHub Actions by commit SHA with Dependabot updates for supply-chain hardening.
- Prettier (or another formatter) for `site/`, decided alongside the Astro builder in spec 003/004.
