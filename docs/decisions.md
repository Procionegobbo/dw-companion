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

## ADR-012: Tracing: Langfuse adapter

Date: 2026-11-07
Status: Accepted

### Context

Spec 006's `Tracer` port is sync and must never raise or block on network (D20): adapters
batch and export off the critical path. Milestone 6 needs every graph node, LLM generation
and anti-hallucination event to show up in Langfuse with session, intent, model, tokens, cost
and latency, and tracing must stay optional for a developer running only with an OpenRouter
key.

### Decision

**The official `langfuse` SDK (5.x, OpenTelemetry-based)** is the tracer adapter
(`backend/adapters/langfuse_tracer.py`, new dependency `langfuse`): it batches and exports on
a background thread, which is how the port's never-block contract is met, and its API names
(`Langfuse.start_observation`, `create_event`, `create_trace_id(seed=…)`,
`propagate_attributes`, `flush`, `shutdown`, the `span_exporter` constructor parameter,
`LangfuseOtelSpanAttributes`) were checked against the installed `langfuse` source. Every
`record_*` call runs inside `try/except Exception`; on failure it logs a WARNING on logger
`backend.adapters.langfuse` naming only the exception class, never the payload, and returns
`None`.

**Langfuse trace id.** A caller-supplied `trace_id` that is already 32 lowercase hex
characters is used as-is; any other value is mapped through `Langfuse.create_trace_id(seed=
trace_id)`, which is deterministic for a given seed. `backend.chat` and spec 008's API pass
`uuid4().hex`, so the id a developer sees printed or logged is the id shown in the Langfuse
UI.

**Session and intent propagation.** Every observation for a trace is opened inside
`propagate_attributes(session_id=…, trace_name="chat_turn")`, so every span and generation for
one turn is grouped under one Langfuse trace named `chat_turn` with the caller's
`session_id`. The tracer remembers `trace_id → intent` from the router node's own attributes
(the router node always runs first; the mapping is bounded at 1,024 traces, oldest evicted),
and every later observation on that trace additionally carries `propagate_attributes(metadata=
{"intent": …}, tags=[f"intent:{…}"])`, so the router's own span is the only one for that turn
missing the tag (it is recorded before routing completes).

**Never block, never raise.** `flush()`/`close()` wrap `client.flush()`/`client.shutdown()`
the same way. Neither method is part of the `Tracer` port; the composition root's
`Runtime.aclose()` and the chat CLI call them directly so a turn's traces are flushed before
the process exits.

**`NullTracer`** (`backend/adapters/null_tracer.py`) is used when both `LANGFUSE_PUBLIC_KEY`
and `LANGFUSE_SECRET_KEY` are empty (spec 007 D18): every method is a no-op returning `None`,
so a developer can smoke-test the assistant with only an OpenRouter key.

**Privacy.** No IP address or other request metadata ever reaches the tracer; only the
caller-supplied `trace_id`/`session_id` identify a turn. Generation inputs (the system prompt
and the user's message) and outputs are sent to Langfuse by design, since that is what makes
a trace useful for debugging prompts — this is a deliberate trade-off, not an oversight.

**Open risk carried from spec 006.** Spec 006 open risk (b) still applies here: the
transitively-added `langchain-core` (via LangGraph) would send LangSmith traces if
`LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` were set. Neither is in `.env.example` or CI, and
this adapter does not set them; the composition root is responsible for keeping both unset in
every deployed environment.

### Consequences

Tests exercise the real SDK against an injected OpenTelemetry `InMemorySpanExporter`
(`backend/tests/adapter_helpers.py` `memory_tracer`, a fresh public key per test client, since
Langfuse keeps one resource manager per public key), so the exported span attributes are
checked against the real wire shape rather than a hand-rolled fake. If a minor `langfuse`
upgrade changes attribute serialisation, only `test_adapters_langfuse.py` should break.

## ADR-013: Model provider: OpenRouter for chat and embeddings

Date: 2026-11-07
Status: Accepted

### Context

Spec 006's `LLMClient` port needs a real provider, and milestone 6 also needs embeddings for
the retrieval index. The project brief's original draft assumed embeddings would come from a
separate provider or a local model; that premise needed re-checking against what OpenRouter
actually offers.

### Decision

**Embeddings come from OpenRouter too, with the same key and SDK** (D1). Verified on
2026-11-05: `GET https://openrouter.ai/api/v1/models?output_modalities=embeddings` lists 44
embedding models, including `openai/text-embedding-3-small` at $0.02 per million input tokens,
and `POST https://openrouter.ai/api/v1/embeddings` answers `401` (the route exists) while an
unknown route answers `404`. `MODEL_EMBEDDINGS` is therefore an OpenRouter model id, not a
separate provider's. **Rejected alternatives**: a direct OpenAI key (a second account, a second
secret, a second billing alert) and a local `fastembed` + `onnxruntime` model (about 150 MB
added to the image and extra Cloud Run cold-start load time, against `min-instances=0`). Both
were rejected for zero marginal benefit over reusing the existing OpenRouter key and SDK. An
override path is kept open without any adapter change: a direct OpenAI key could be added later
as `EMBEDDINGS_API_KEY`/`EMBEDDINGS_BASE_URL` building a second `AsyncOpenAI` client in
`backend/composition.py`, since the embedder takes an injected client. **Cost estimate**: a
full index build is under $0.05; a query embedding (~30 tokens) costs about $0.0000006.

**Committed index embedding model**: `openai/text-embedding-3-small` (D2) — cheapest
well-known general embedding model with an 8,192-token context. It is never hardcoded: it is
the value of `MODEL_EMBEDDINGS` at index-build time, recorded in the index manifest, and the
composition root refuses to start if `MODEL_EMBEDDINGS` ever disagrees with the manifest.

**OpenRouter chat adapter** (D12) uses the official `openai` SDK (`AsyncOpenAI`,
`base_url="https://openrouter.ai/api/v1"`). Structured requests set
`response_format={"type": "json_schema", ...}` with `provider.require_parameters = true`, so
OpenRouter only routes to providers that honour the schema; every request sets
`usage.include = true` so cost is reported. Timeout 30s, one SDK-level retry.

**Model ids come only from env** (D13): `MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER`,
`MODEL_EMBEDDINGS`, all required, kept empty in `.env.example`. Suggested starting values for
local smoke runs — router/classifier `openai/gpt-4.1-nano`, answer `openai/gpt-4.1-mini`,
embeddings `openai/text-embedding-3-small` — are recorded here only, **provisional until spec
010's measured choice** replaces them with eval evidence.

**`LLMResponse` gains one additive field** `cost_usd: float | None = None` (D11), filled from
OpenRouter's reported `usage.cost`. **Port errors never leak secrets** (D22): every provider
failure becomes `PortError` naming the operation, the exception class and, for HTTP errors, the
status code — never the API key, headers or response body.

### Consequences

The runtime needs exactly one provider account and one SDK for both chat and embeddings. If
OpenRouter ever omits `usage.cost` for a model, `cost_usd` is `None` and Langfuse shows no cost
for that generation (open risk, mitigated by a Langfuse custom price as a UI-only fallback). The
provisional model ids must be revisited once spec 010 has eval evidence; nothing in the code
enforces that, so it is a manual follow-up.

## ADR-014: Retrieval — section chunks, NumPy + in-house BM25 hybrid, committed index

Date: 2026-11-07
Status: Accepted

### Context

Milestone 6 needs a retriever over the Dungeon World rulebook that returns distinct,
citation-sized sections for a rules question, built and queried without a managed service
(handoff 4.3: no managed vector DB) and without opening a paid API call from CI.

### Decision

**Vector store: a NumPy matrix** (`embeddings.npy`, float32, L2-normalised rows) plus
brute-force cosine similarity — no Chroma, LanceDB or FAISS (D3). The corpus is one book (a few
hundred chunks × 1,536 dimensions, about 2-3 MB); a matrix-vector product costs well under a
millisecond. Chroma pulls a SQLite stack and its own embedding runtime, LanceDB pulls
`pyarrow`, and FAISS is built for millions of vectors — all unjustified for this size. The index
artifact (`data/index/{manifest.json, chunks.json, embeddings.npy}`) is **committed to git**
and rebuilt by `python -m backend.adapters.retrieval.build`, the same "built offline, baked into
the image" pattern as spec 002's committed `data/normalized/` (D4); a freshness test fails when
`chunks.json` no longer matches the chunks derived from the committed normalized data, and CI
never calls a paid API.

**BM25 is implemented in-house** (`bm25.py`: Okapi BM25, `k1=1.2`, `b=0.75`, non-negative IDF;
D5), tokenized by NFKC-normalise, lower-case, `[a-z0-9]+` tokens, no stemming or stop-words
(D6) — exact game terms ("hack and slash") matter, and IDF already down-weights common words.
`rank-bm25` was rejected (untyped, last released 2022, needs our tokenizer anyway) and `bm25s`
was rejected (adds `scipy`); the in-house formula is ~40 lines, fully unit-testable, and
milliseconds to build for ~400 short documents.

**Fusion: Reciprocal Rank Fusion** (D7) of the top `CANDIDATES = 30` vector hits and the top 30
BM25 hits (score > 0), `score = Σ 1/(RRF_K=60 + rank)`, ties broken by chunk order, deduplicated
by `section_id` (first wins), cut to `k`. RRF needs no score normalisation between the cosine
and BM25 scales and is the standard simple hybrid.

**Chunking** (D8-D10): one chunk per section with non-empty `text_markdown`, except a move's
`section_id` is replaced by that move's own chunk (`type="move"`), chapter `thanks` is excluded,
and a section longer than `MAX_CHUNK_CHARS = 6000` is split on blank-line block boundaries
(never mid-block; move chunks are never split). Index text is
`"{chapter title} > {title}\n\n{text}"`, truncated to `EMBED_MAX_CHARS = 24000` characters for
embedding only; `anchor_url = section_url(section_id)` for every chunk (the spec 004 citation
contract).

**Rebuild command**: `uv run --env-file .env python -m backend.adapters.retrieval.build
[--normalized DIR] [--out DIR]`, needs `OPENROUTER_API_KEY` and `MODEL_EMBEDDINGS`, writes
nothing on any failure.

### Consequences

No managed vector service, no extra infrastructure, and the index is reviewable in diffs like
any other committed data file — at the cost of a ~2-3 MB binary (`embeddings.npy`) in git,
replaced wholesale on each rebuild (acceptable at this corpus size). The chunk-size constants
are unmeasured against the real data pin and are tunable in spec 010 once the build CLI's
printed statistics are reviewed. BM25's lack of stemming is a deliberate trade-off that spec
010 may revisit if eval recall shows term-form misses.

## ADR-015: Chat API: SSE protocol, guardrails and in-memory limits

Date: 2026-11-08
Status: Accepted

### Context

Milestone 7 exposes the spec 006 assistant over HTTP so the browser widget can use it.
Handoff 7 requires every LLM call to sit behind guardrails — a max input length, a global
daily spend cap and a per-IP rate limit — checked before any model call, and forbids storing
or logging raw visitor IPs. The assistant graph has no streaming hook and nothing aggregates
per-call cost, so both had to be added first (`Assistant.stream`, `MeteredLLMClient`).

### Decision

**Three SSE event types on one stream**: `status {"step"}` after each graph node completes,
`reply {trace_id, kind, text, citations, move}` once as the terminal event of a successful
turn, `error {"code", "message"}` once as the terminal event of a failed turn. **No partial-
token (`delta`) event**: spec 006's citation validator needs the complete answer before any
of it can be shown, so raw tokens would surface unvalidated `[[id]]` markers and undermine the
project's anti-hallucination signal. Clients ignore unknown event names, so a `delta` event can
be added later without breaking the widget. Rejections *before* streaming starts are plain
HTTP JSON (`{"error": {"code", "message"}}`), not SSE, since every guardrail decision is made
before any LLM call and no stream needs to be opened; `429` and `503` carry `Retry-After`.

**Guard order for `POST /api/chat`**: content type → body size (16 KiB, read incrementally) →
JSON/schema → message length → global spend cap → per-client rate limit (which records the
request) → stream. Rejected requests never reach the graph, and only a request that passes
every guard counts against the rate limit — a request rejected by an earlier guard, including
the spend cap, never touches the limiter.

**Defaults**: `CHAT_RATE_PER_MINUTE=5` (sliding 60s window), `CHAT_RATE_PER_DAY=50` (per UTC
day, checked first), `CHAT_DAILY_BUDGET_USD=1.00` (sum of provider-reported `cost_usd` for
completed LLM calls in the current UTC day). When a response omits `cost_usd`,
`MeteredLLMClient` counts a deliberately high `FALLBACK_CALL_COST_USD = 0.01` instead (logged
once per process at WARNING) so an under-reporting provider exhausts the budget faster rather
than bypassing it. At most `MAX_TRACKED_CLIENTS = 10000` rate-limiter keys are kept, least
recently seen evicted first, bounding memory under an IP-rotation attack (backed up by the
global spend cap regardless of key count).

**Limits are in-memory and per-process — the only implementation in scope.** A restart or a
second Cloud Run instance each start counting from zero, so daily spend can exceed the cap
across instances. Three mitigations, none built here: spec 011's `max-instances=1`, owner
billing alerts, and an OpenRouter per-key credit limit (an owner action). A shared store
(Firestore, Redis) is a *Future Consideration* — out of scope for a demo, since it adds a
paid or managed dependency and ops work. Python's single-threaded asyncio with no `await`
between a limiter's check and its record means no locks are needed.

**Client IP and trusted hops**: with `CHAT_TRUSTED_PROXY_HOPS = n` (default `0`), the client
IP is the n-th entry from the right of `X-Forwarded-For`; with `n = 0`, or fewer than `n`
entries, it is the socket peer address (`"unknown"` if none). Taking entries from the right
ignores values a client prepends. Only the HMAC-derived key (`ClientKeyer`, a per-process
random salt) is ever stored in the limiter or looked up — never the raw IP — and the API logs
only rejection codes, trace ids and exception class names, never IPs or message text.

**Dependencies**: `fastapi` — the API framework named in the project brief (handoff 4.1);
typed request models and an ASGI app Cloud Run can serve. `uvicorn` — the standard ASGI server
to run the app locally and in the container (spec 011). `starlette.testclient` (used for
tests) is backed by `httpx2`, already installed transitively by `openai` (spec 007), so no new
dev dependency was needed. FastAPI's native `EventSourceResponse` was not used in favour of a
10-line SSE frame formatter, trivially unit-testable and independent of a recent FastAPI API.

**Contract fixture**: `backend/tests/fixtures/chat_reply_examples.json` binds the backend's
`reply_payload` and the frontend's protocol schema to the same exact JSON, so a backend test
and a frontend test both assert against the one file.

### Consequences

The API adds no new infrastructure (no database, no managed rate-limit or billing service) at
the cost of the stated per-process limitation, which must be closed before a sustained public
launch (spec 011's open risk). The `MeteredLLMClient` wrapper keeps the graph and every other
adapter unaware that a budget exists. Token-level streaming, shared limiter/ledger state and a
cancel button remain *Future Considerations*.

## ADR-016: Chat widget: vanilla island on /assistant/, same-origin fetch

Date: 2026-11-08
Status: Accepted

### Context

The chat API (ADR-015) needs a browser front end. Spec 004 chose an Astro site with no UI-
framework integration, and handoff 4.5 says to "keep it light." The widget streams progress and
a structured reply over SSE, must render LLM-authored text safely, and must follow spec 004's
citation URL contract (`sectionUrl`/`moveUrl`) rather than build its own hrefs.

### Decision

**`fetch("/api/chat")` with the project's own SSE parser, not `EventSource`.** `EventSource`
only issues GET requests with no body, and its automatic reconnection would silently re-send
(and re-bill) a turn on a dropped connection. A relative, same-origin path needs no build-time
API URL and no CORS; in development the Astro dev server proxies `/api` to the local FastAPI
app (Vite `server.proxy`, `astro.config.ts`), reproducing the production same-origin layout
(spec 011's single container) locally.

**No UI framework.** Spec 004 adopted no React/Vue/Svelte integration, and one form plus a
message list needs no framework. The widget is a single vanilla-TypeScript island: an Astro
component (`ChatWidget.astro`) with a processed `<script>` that imports and calls
`mountChatWidget()` and references no other globals.

**A dedicated `/assistant/` page, linked from the header, with citation and move links opening
in a new tab.** Every other page on this static site is a full navigation, so a widget present
on every page would lose the conversation on every citation click. A dedicated page keeps the
transcript alive for the length of the visit (no `sessionStorage` needed yet — a *Future
Consideration*) and keeps every rules page script-free. New-tab links let a visitor follow a
citation to check the rules without losing their place in the conversation.

**Rendering is safe by construction.** All server-authored text (the reply, citation titles,
move text) is placed with `textContent`/`createTextNode`, never `innerHTML` — enforced by
`grep -rn "innerHTML" site/src/lib/chat` finding nothing. Every `href` is built from the
schema-validated payload's own `url`, which the protocol schema requires to equal
`sectionUrl(section_id)` or `moveUrl(move_id)` — the same builders every other page uses — so a
payload cannot carry an arbitrary or `javascript:` href. `[[section_id]]` markers become
numbered `[n]` links only for ids present in `citations`; unrecognised markers are dropped.

**DOM tests use `happy-dom`** (a new `site/` devDependency), since escaping and link-building
are security properties that need real DOM assertions, not just string matching. Pure modules
(`sse.ts`, `protocol.ts`, `client.ts`) stay in the default `node` test environment.

### Consequences

The widget adds one script to one page and no client-side framework or build-time API URL.
Reconnection, retries and a cancel button are left to the visitor retrying manually — a cancel
button backed by `sendChat`'s existing `AbortSignal` support is a *Future Consideration*, as is
persisting the transcript across same-tab navigation.

## ADR-017: Evaluation harness

Date: 2026-11-08
Status: Accepted

### Context

Spec 010 (model tuning) and the README results table (spec 012) both need trustworthy,
reproducible numbers for router accuracy, rules-answer quality and move classification. The
assistant graph (ADR-011) has no entry point below the router for a cheaper check, and the
labels for "is this answer correct" can only come from an experienced GM, never from the model
under test — otherwise a config could grade its own homework.

### Decision

**Rule R-LABEL governs every row of every dataset, stated here verbatim:**

1. Labels are written or validated by the project owner (an experienced GM). They are never
   generated by the model under test. That means no model configured in any
   `evals/configs/*.toml` file, and no output of the assistant itself. Agents, including whoever
   implements this spec's stories, may draft candidate rows. A candidate row is untrusted until
   the owner has reviewed it.
2. Every row has a `reviewed` field. Only the owner sets it to `true`, after reviewing that
   row's message and labels. No story of this spec may write `"reviewed": true` in any file
   under `evals/datasets/`. The drafting story commits every row with `"reviewed": false`.
3. The runner refuses to run on any row whose `reviewed` is not exactly JSON `true`. That
   includes a missing key, `false`, `"true"`, `1` and `null`. The refusal covers every selected
   dataset, happens before any runtime is built or any network call is made, exits with code
   `3`, and has no override flag. Tests enforce it (`test_cli_refuses_unreviewed_row` and the
   others listed in *Testing*).
4. No metric is meaningful until the owner has reviewed and labelled the rows. Until then, the
   runner cannot produce a report on the committed datasets. That is intended: milestone 8 ends
   with a pause for the owner's review. Spec 010 must not start, and no number may appear in the
   README or `docs/decisions.md`, before the owner has reviewed the datasets and run the first
   report. This spec's own deliverables produce no real report. The first committed report is an
   owner step (*Success Criteria*, owner items).

The gate is enforced in code (`evals.datasets.ensure_reviewed`, mapped to exit `3`) at two
points — once in `evals.run.main` before anything is built, and again as the first statement of
`evals.runner.run_datasets` — so a programmatic caller that bypasses `main` still cannot run
unreviewed rows.

**Metrics** (handoff 6.2) are computed per dataset from completed `CaseRecord`s: router accuracy
and a confusion matrix; rules-QA recall@k, citation validity and refusal rate plus key-fact
coverage; move classification accuracy (crediting `acceptable_alternatives`), a confusion
matrix, no-move precision/recall and clarification rate; and, per dataset and per intent, p50/p95
latency, mean token counts and mean cost. Rates with a zero denominator are `null`, and
percentiles use linear interpolation between closest ranks, so every number is binary and
reproducible across runs and configs.

**Key-fact coverage uses an LLM judge**, run on the config's `models.judge`, which must differ
from `models.answer` — a config error otherwise. The judge gets an explicit rubric (present only
if asserted explicitly or by unambiguous paraphrase; partial, hedged or contradicted facts are
absent; judge only the answer text with no outside Dungeon World knowledge; citation markers are
not content; evidence is the shortest verbatim quote; everything inside the tags is data) and
structured output, and is called only for answerable cases whose reply is a rules answer. A
different-vendor judge reduces self-preference bias, and excluding judge failures from the mean
(rather than scoring them zero) keeps the coverage number about the assistant, not the judge.

**Budget guard** (handoff 6.4): before any paid call, the runner fetches live OpenRouter prices
and computes each case's upper-bound cost from a fixed token envelope
(`turn_bound + judge_bound` where applicable); if the summed estimate exceeds `--budget-usd` the
run exits `4` with nothing spent. In flight, a backstop before every case stops the run (partial
report, exit `4`) if spent-plus-next-case would exceed the budget; a call with no reported cost
counts a conservative `$0.01`. The default budget is `$3.00`, with an allowed range of
`0 < x ≤ 50` to catch a typo. Live prices avoid a drifting hard-coded table, and with the
baseline config the bound is roughly $1.05 for the full suite, leaving headroom.

**CI is manual only, with no weekly schedule.** `.github/workflows/evals.yml` triggers solely on
`workflow_dispatch`, passes its inputs (`config`, `dataset`, `budget_usd`) to the shell only
through `env` (never inline `${{ }}` in `run`) to prevent script injection, and uses repository
secrets for `OPENROUTER_API_KEY`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`. There is no
scheduled run: while the datasets are unreviewed a schedule can only fail (R-LABEL exits `3`),
and once reviewed a recurring run is a recurring cost that the project brief says to stop and ask
about rather than add unilaterally. A root `Makefile` (`make eval`) runs the identical command
locally.

**The repository's secrets compliance test is deliberately narrowed.**
`test_ci_workflows_reference_no_secrets` (ADR-006) could not otherwise coexist with a workflow
that legitimately needs paid-API credentials, so it now exempts exactly
`SECRET_WORKFLOWS = frozenset({"evals.yml"})`, while still failing if `.github/workflows/` has no
`*.yml` file and still covering `ci.yml`. A new test,
`test_secret_workflows_are_manual_only`, asserts that every allow-listed file that exists
contains `workflow_dispatch` and none of `pull_request`, `push:` or `schedule:` — keeping the
real invariant (no PR- or push-triggered workflow can reach a paid API) enforceable in code
rather than only in review.

### Consequences

The harness can only ever report real, owner-trusted numbers: an unreviewed dataset blocks every
run, and spend is bounded before and during every run. Two open risks are accepted for now: (c)
the token envelope may under-estimate an unusually long prompt, bounded by the in-flight backstop
to at most one case's overshoot past the budget; and (d) judge reliability is unmeasured —
per-fact evidence quotes are recorded in every report for owner spot-checks, and validating the
judge against owner labels is left as a *Future Consideration*. Any later workflow that needs a
secret (e.g. spec 011's deploy) must add itself to `SECRET_WORKFLOWS` under the same
manual-only or `main`-only reasoning rather than weakening the test further.
