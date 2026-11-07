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

## ADR-007: Ingestion: stdlib parser, chapter manifest, IDs, committed output as snapshot

Date: 2026-11-07
Status: Accepted

### Context

The ingestion pipeline turns 37 InDesign-flavoured XML files into three JSON files that
every later spec (site, domain types, retrieval, move classifier) treats as a fixed-shape
contract. The source has no reliable chapter title or book order, no stable identifiers,
and nothing to compare a rebuild against short of trusting the code.

### Decision

The parser uses **Python stdlib only** (`xml.etree.ElementTree`, `dataclasses`, `json`,
`argparse`, `logging`, `re`, `unicodedata`) — no `defusedxml`, `lxml` or snapshot library;
the input is pinned, trusted upstream text, so expat's built-in entity-expansion limits are
enough. Chapters are defined by a **hand-written manifest** (`ingestion/manifest.py`,
file + chapter id + title + book order); the build fails loudly if `text/` ever disagrees
with it. **Section granularity is chapter → `h1` → `h2`**: deeper headings stay inside
their section's `text_markdown`, giving citation-sized sections without one-line sections
for every monster or list item, and with no text duplicated between parent and child.
**IDs derive from the source once**: a chapter section's id is the chapter id; other
section ids are `{chapter_id}/{slug(title)}`, de-duplicated with a numeric suffix on
collision; move ids are `slugify(name)`; class ids are their chapter id — stable,
citation-friendly, and mapping naturally to site paths. The **unknown-markup threshold is
0** by default (`--max-unknown N` to raise it locally): every tag, attribute, `aid:pstyle`
and `aid:cstyle` value at the pin was inventoried, so any unknown occurrence means upstream
changed and a human must look — the text is still kept ("tolerant"), but the build fails
("loud"). The **committed `data/normalized/*.json` files are themselves the snapshot**: a
test rebuilds in memory and compares byte-for-byte against them, with no snapshot library
needed; regenerating is `uv run python -m ingestion`. **Output format** is fixed: one JSON
array per file, UTF-8, `ensure_ascii=False`, `indent=2`, keys in the *Data Model* field
order, LF line endings, a trailing newline, and typographic characters (’ “ ” — – …) kept
verbatim with only `✴` and zero-width spaces stripped.

### Consequences

Every later spec reads deterministic, diff-reviewable JSON with stable ids and no new
runtime dependency. An upstream source change that adds markup outside the known inventory
fails the build rather than silently dropping or mis-rendering text. Regenerating the
snapshot after a parser change is a single command, and the diff is the review.

## ADR-008: Outcome bands follow the source; extended stat vocabulary

Date: 2026-11-07
Status: Accepted

### Context

The project brief (handoff milestone 2) describes move cards with "three outcome bands" —
strong hit, weak hit, and miss — implying every move states all three. Reading the actual
source (`Moves.xml`, and `Playing_the_Game.xml`'s explicit statement of the rule) shows this
isn't true: most moves never say what a 6- does, leaving it to the GM by the general rule, and
a handful of moves don't roll at all. The brief also doesn't give `stat` a type, but the source
needs more than the six ability scores to describe every move accurately.

### Decision

**This discrepancy is deliberate, and the source wins (handoff 12).** `outcomes.miss` is
`null` whenever the move's text states no miss outcome — only Last Breath, Take Watch, Carouse
and Recruit do. Inventing miss text for the other 11 rolled moves would put words in the
authors' mouths and break the project's "quoted from structured data, not regenerated"
principle; instead, milestone 2's acceptance is restated as every rolled move having `trigger`,
`stat`, `strong_hit`, `weak_hit`, and an `outcomes` object with all three keys present
(`miss` possibly `null`). Six moves (Encumbrance, Make Camp, Level Up, End of Session, Recover,
Bolster) don't roll at all, so both `outcomes` and `stat` are `null` for them.

`stat` is typed as `"STR" | "DEX" | "CON" | "INT" | "WIS" | "CHA" | "BOND" | "VARIES" | "NONE"`
or `null`, instead of just the six abilities: `BOND` covers Aid or Interfere (`roll+Bond`),
`VARIES` covers Defy Danger (the player picks the stat by approach, not a fixed `roll+Stat`),
and `NONE` covers rolled moves with no stat at all (Last Breath, Carouse, Recruit).

### Consequences

`moves.json`'s `miss` field is genuinely nullable and `stat` has three values beyond the six
abilities; any later spec that renders a move card or feeds `stat` into the move classifier
(specs 005/006) must accept this vocabulary rather than assuming three non-null bands and six
possible stats. Spec 006's move-card explanation can cite `Playing_the_Game.xml`'s own general
rule for why a 6- outcome is unstated.

## ADR-009: Domain layer — stdlib types, mirrored ingestion shapes, injected dice randomness

Date: 2026-11-07
Status: Accepted

### Context

The backend needs a pure, innermost layer (handoff 4.1) for rulebook types and dice
resolution, buildable in parallel with the ingestion pipeline (spec 002) rather than
depending on it, and testable without any real randomness.

### Decision

**Stdlib only**: frozen, slotted `dataclasses` with `__post_init__` validation and
`typing.Literal` vocabularies — no Pydantic, no new dependency; Pydantic arrives with
FastAPI at the API boundary (spec 008), where it belongs. **The domain re-declares the
spec 002 JSON shapes rather than importing `ingestion.models`**: the runtime container
must not need the offline ingestion package, and compatibility is proven by tests
(inline fixtures plus a test that parses the committed `data/normalized/*.json` when
present) rather than by sharing code. The `Stat` vocabulary extends the six abilities
with `BOND`, `VARIES` and `NONE` (mirroring spec 002 D9); `AbilityStat` is the narrower
six-value vocabulary for the move classifier's output. Naming keeps `Outcomes` (plural,
a move's three band texts) distinct from `Outcome` (singular, the resolved result of one
roll on one move) — both already fixed names from the handoff and spec 002.

**Dice resolution is deterministic and the band rule follows the source exactly**: a
total **>= 10** is `strong_hit`, **7-9** is `weak_hit`, and **<= 6** is `miss`, with no
natural-roll special cases. **Randomness is injected**: `roll(rng, modifier)` takes any
object satisfying the `RandomSource` protocol (`randint(a, b, /) -> int`); the domain
never imports `random` and holds no global RNG, so production supplies a `random.Random`
and tests supply a seeded one or a scripted fake. **Only `backend.domain.dice.roll`
produces dice values — the LLM never invents a roll**; the graph's `roll` tool (spec
006) calls this primitive and nothing else generates dice. The **modifier is optional
and bounded to -10...+10 inclusive** (`bool` rejected): `modifier=None` yields a `Roll`
with dice but no total or band, letting a caller ask for the modifier before committing
to one; `band_with(modifier)` reports the band for any modifier without needing a full
`Roll`. Real stats run -3...+3, so a range of 10 in either direction comfortably covers
forward/ongoing bonuses while rejecting nonsense the LLM might otherwise pass as a tool
argument.

### Consequences

`backend/domain/` depends on nothing but the standard library and is importable and
testable before spec 002's ingestion output exists, at the cost of ~20 duplicated lines
of type declarations between `backend/domain/rulebook.py` and `ingestion/models.py`,
kept honest by the compatibility tests rather than by sharing code. Any later caller of
`roll` (spec 006's tool) must supply its own `RandomSource`; none is created implicitly,
so a forgotten seed is a visible wiring bug rather than silent nondeterminism.

## ADR-010: Static site: Astro, URL contract, data loading and link check

Date: 2026-11-07
Status: Accepted

### Context

The static rules site (spec 004) needs a build-time-only Astro application reading spec
002's committed `data/normalized/*.json`, a URL scheme stable enough to be the assistant's
citation target (specs 007, 008), and a tooling migration from spec 001's placeholder that
keeps CI working across the swap.

### Decision

**URL scheme (the citation contract):** section pages are served at **`/rules/<section_id>/`**
and move pages at **`/moves/<move_id>/`**, trailing slash always, with the id inserted
verbatim — no encoding, no lowercasing, no title or slug ever contributing to a URL. Separate
`/rules/` and `/moves/` prefixes avoid the collision between the `moves` chapter id
(`/rules/moves/`) and the moves index (`/moves/`); slash-containing section ids
(`moves/hack-and-slash`) map directly onto nested paths. **Specs 007 (`anchor_url`) and 008
(citation links, move card) must build their links with exactly these formulas.**

**Astro** (current stable major, static output, `trailingSlash: "always"`,
`build.format: "directory"`, no `site`/`base` set) renders one page per section (including
chapter roots) and one page per move, plus a moves index, home and 404 page. **Data is loaded
with a Vite `?raw` import + `JSON.parse` + Zod `.strict()` validation** in a plain module
(`site/src/lib/rulebook.ts`), not Astro content collections, because content-collection and
Zod import paths have moved across Astro majors while `?raw` imports are stable Vite behaviour,
avoid TypeScript inferring a type from a megabyte-scale JSON literal, and stay importable from
Vitest. Every validation problem is collected before one `RulebookError` is thrown, so a spec
002 shape change fails the build loudly and completely rather than one error at a time. Tests
run under **Vitest**, in two suites: unit tests needing no build, and a built-output link check
that fails (never skips) if `dist/` is missing.

**Tooling migration keeps spec 001's script-name contract** (ADR-005): `lint` stays
`"eslint ."`; `typecheck` becomes `"astro check"` (covers `.astro` and `.ts` files); `dev`,
`build`, `preview` and `test` are added. `site/tsconfig.json` extends Astro's strict preset and
keeps `noUncheckedIndexedAccess: true`, so strictness is not lowered. `engines.node` tightens
to `>=22.23.4` (Astro's own requirement); `site/.nvmrc` stays `22`. CI's Astro commands set
`ASTRO_TELEMETRY_DISABLED: "1"` as a step-level `env` — not a credential, so ADR-006's
no-secrets rule still holds.

**Attribution footer** on every page carries the CC BY 3.0 credit and source link, the
adaptation statement, the SRD 5.1 / CC BY 4.0 notice, the unofficial-project statement and the
MIT-for-code statement, with no link to this project's own repository (its public URL is not
yet fixed).

This extends **ADR-005** (frontend placeholder tooling): the `lint`/`typecheck` script names it
fixed are kept across this swap from `tsc --noEmit` to `astro check`.

### Consequences

Citation code in specs 007 and 008 can hard-code the two URL formulas instead of calling into
the site, since they are now a recorded contract; changing them later breaks every citation link
already issued. The site fails its own build on any drift from spec 002's JSON shapes, with a
single multi-line error rather than a silent partial render. Developers on Node 22 older than
22.23.4 must upgrade to run `site/`.

## ADR-011: Assistant graph: LangGraph behind ports, deterministic citations, dice and outcomes

Date: 2026-11-07
Status: Accepted

### Context

Spec 006 turns one user message into one structured reply, with a router, a rules branch and
a move branch that must never let the LLM invent a rule citation, a dice result or an outcome
band (handoff 4.4, 7). The orchestration needs typed state, conditional branching and
node-level streaming hooks for spec 008's SSE, without locking every port and node to one
provider's API.

### Decision

**LangGraph is the orchestration library** (current major, added via `uv add langgraph`,
which also pulls in `langchain-core` and `pydantic` transitively, neither imported by our own
code): it is the library the project brief's architecture diagram names (handoff 4, 4.1
`graph/`), and it gives typed state, conditional edges and node-level streaming, which spec
008's SSE needs. **LangGraph is confined to `backend/graph/builder.py`**, the only module that
imports `langgraph.*`; every node is a plain `async` function over a `TypedDict` state, and
callers use an `Assistant` wrapper, never a LangGraph type, so a major-version upgrade or a
typing quirk touches one file. **Ports are async where they do I/O** (`LLMClient.generate`,
`Retriever.retrieve`) **and sync where they don't** (`Tracer`, `RulebookRepository`).
**`LLMClient` is one generic method** taking an `LLMRequest` (`role`, `system`, `user`,
`max_tokens`, `temperature`, optional JSON Schema); prompts, schemas and output validation
live in `graph/`, so a thin adapter is easy to swap later.

**Structured LLM output is parsed by deterministic code** (`graph/llm_outputs.py`): any
violation of the required shape is an invalid output, which ends the turn with the fixed error
reply and a traced event, with no retry. **The dice roll is a deterministic graph node, never
an LLM function-calling tool**: whether to roll and with which modifier come only from the
caller-supplied `TurnInput` (`roll_requested`, `modifier`), the `roll` node calls
`backend.domain.dice.roll`, and the `outcome` node calls `backend.domain.outcome.
resolve_outcome` — the LLM never invents a roll or an outcome band. **Outcome bands are never
part of LLM text**: `Reply.text` holds only prose (an LLM explanation or fixed copy); the
bands live solely in `MoveCard.outcomes` (verbatim from the `Move`) and the rolled result in
`MoveCard.outcome` / `MoveCard.bands_by_modifier`. **Citations are inline markers
`[[<section_id>]]`** in the rules answer's plain text, validated by deterministic code with no
further LLM call: the citation validator keeps a marker whose id is in the retrieved set and
removes any other marker together with the whitespace run immediately before it, returning
citations in first-appearance order — no citation ever reaches the reply unless the retriever
actually returned that section. **A low classifier
confidence (`< clarify_threshold`, default `0.6`)** always asks one deterministic clarifying
question instead of guessing which move triggered.

**Tracing is explicit**: a wrapper records one `NodeTrace` per executed node (latency from an
injected clock, so tests stay deterministic), one `GenerationTrace` per LLM call (full request
and response, for spec 007's Langfuse cost/latency reporting), and named `TraceEvent`s for
anti-hallucination and error signals. `trace_id` and `session_id` are supplied by the caller;
no IP address ever enters the graph (handoff 7).

### Consequences

Dice, outcome text and citations are anti-hallucination by code rather than by prompt alone: an
LLM that misbehaves can still only produce text that gets stripped or never reaches the reply.
Swapping LangGraph's major version, or a future orchestration library entirely, touches only
`builder.py`. The transitively-added `langchain-core` sends LangSmith traces when
`LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` is set; neither is in `.env.example` or CI, and
the backend tests' no-network guard (D24) would make such a call fail loudly rather than
silently phoning home, but spec 007's composition root must keep both env vars unset in every
deployed environment.
