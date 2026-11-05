# 012 - README polish and launch

**Status:** spec — ready for story-creator.
**Depends on:** every prior spec. In particular: 001 (README stub, `## Attribution` compliance test, ADR format D15, `REPO_ROOT` test pattern), 002 (21 basic and special moves, ADR-007/008), 004 (URL contract, ADR-009, "Not stated by this move."), 005 (`backend/domain/dice.py`), 006 (graph, deterministic citations/dice/outcomes, fixed copy), 007 (OpenRouter, hybrid retrieval, Langfuse), 008 (guardrails, SSE, widget), 009 (R-LABEL, metrics, `make eval`, report files), 010 (`make compare`, comparison table markers, decision rule), 011 (Cloud Run, `infra/runtime-env.yaml`, `Live URL:` in `docs/deploy.md`).
**Start condition:** the stories need specs 001–011 **built** (not their owner gates), because the README links to files and ADRs they create. The owner-gated data is filled in later (*Owner Gate*).
**Reference:** `HANDOFF_dw-companion.md` sections 1, 3, 4, 7, 10 (milestone 11), 11, 12.

## Feature Name & Description

**The final `README.md`.** It is a rewrite of the root README into the nine sections handoff 11 requires, in that order. The README is the first thing a hiring manager reads, so it must explain the problem, show the demo, say where AI is and is not used, and give the measured evidence (evals, cost, latency) with the trade-offs behind it.

**Current state.** None of the code exists on disk yet. Specs 001–011 are approved and will be built before this one. Apart from `HANDOFF_dw-companion.md` and `STORIES/`, every path in this spec is new: it is created either by specs 001–011 (marked "(new in 00N)" in *Impact on Existing Code*) or by this spec (marked "(new)"). Paths that appear inside the README template (`backend/domain/dice.py` from 005, `backend/graph/citations.py` from 006, `evals/datasets/` from 009, and so on) are checked by `test_readme_relative_links_resolve`. When this spec starts, `README.md` has spec 001's stub: title, tagline, `> Status: under construction.`, `## Attribution`, `## License`. It also has a `## Development` section that specs 004, 007, 008, 009, 010 and 011 extended with command subsections. None of the nine handoff sections exist.

**What the stories deliver, and what they cannot.** This split is binding:

| Fully written by the stories | Owner-gated placeholder slots (filled by the owner later) |
|---|---|
| 1 Problem statement · 3 What the assistant does / doesn't do with AI · 4 Architecture diagrams and walkthrough · 7 Trade-offs with ADR links · 8 What I'd do next · 9 Attribution and licensing · all of section 5's prose, metric definitions, table layout and reproduction commands · all of section 6's guardrails, table layout and measurement notes · section 2's prose and "things to try" | `demo-url` (spec 011 owner gate) · `demo-gif` (needs the live deploy) · `eval-results` (spec 009/010 owner gates) · `eval-comparison` (spec 010 owner gate) · `cost-latency` (spec 010 owner gate) |

**No-fabrication rule** (inherited from specs 009 R-LABEL point 4 and 010 D1): no story writes an invented, estimated or example eval, cost, latency or URL value into `README.md`. A slot holds only the placeholder token until the owner fills it from a committed file.

**In scope:** the README rewrite, moving the developer commands to `docs/development.md`, one guard test file, and the owner fill procedure.

**Out of scope:** any code, config or behaviour change; new ADRs; changes to `ATTRIBUTION.md`, `LICENSE`, the site footer, `docs/decisions.md`, `docs/architecture.md`, `docs/deploy.md` or `evals/README.md`; a CI badge or custom domain.

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Placeholder convention: the literal token `TODO-OWNER(<slot-id>)`, visible in the rendered README.** Every slot has (a) one HTML comment `<!-- TODO-OWNER(<slot-id>): <fill instructions> -->` and (b) visible pending text or table cells containing the same token. Filling a slot means replacing both with the real content. There are exactly five slot ids: `demo-url`, `demo-gif`, `eval-results`, `eval-comparison`, `cost-latency`. **Completion check:** `grep -n "TODO-OWNER" README.md` prints nothing (exit status 1). | One grep finds both the hidden instructions and the visible gaps. A visible token is honest: a reader before launch sees "pending", not an empty table. An HTML comment alone would hide gaps, and a bare `TBD` collides with ordinary prose. The `(slot-id)` suffix lets the owner fill slots independently: deploy-dependent slots can be filled before eval-dependent ones. |
| D2 | **Implementation-time values use a second token family, `{{adr:<key>}}`, which exists only in this spec's template.** The story resolves every one of them (see *ADR Reference Tokens*). The committed README never contains `{{`, and a test enforces it. | ADR numbers after ADR-009 are "next free number at implementation time" (specs 005 D16 … 011 D17), so they are unknown now but known when the story runs. They are not owner data, so they must not use the owner token. |
| D3 | **Section headings are fixed** (*README Content*), in handoff 11 order, and are the only `## ` headings in the README. `## Attribution` keeps its exact text, so spec 001's `test_readme_has_attribution_section` still passes. Licensing goes inside that section, and the stub's `## License` heading is removed. | Handoff 11 item 9 is "Attribution and licensing", one section. A fixed list makes the order testable. |
| D4 | **`## Development` moves verbatim to `docs/development.md` (new).** Headings are promoted one level (`## Development` → `# Development`, `### X` → `## X`), and relative links are rewritten for the `docs/` location. The README links to it at the end of *Architecture*. The stories implement the move as specified. If the owner later prefers the commands back in the README, that is an optional post-launch change: place `## Development` after `## Attribution` and allow it in the order test. | Handoff 11 says "in this order, concise". By spec 011 the Development section has six subsections of commands, which would put roughly 80 lines between the nine sections. No spec or test links to a README Development anchor (checked across specs 001–011), so moving it breaks nothing. |
| D5 | **Section 5 (eval) shows two tables.** First, a results table for the production configuration (quality metrics only, with a "What it measures" column written now). Second, the comparison block pasted verbatim from spec 010's comparison file, between its `<!-- comparison-table:start -->` / `<!-- comparison-table:end -->` markers. Section 6 shows cost and latency for the production configuration. All three tables are filled from **the committed comparison file** (the chosen config's column), not from raw report JSON. | Handoff 6.3 asks for "a results table … plus one comparison". Spec 010's comparison already computes every headline metric, plus cross-dataset cost per query and latency, with fixed formatting (spec 010 *Comparison Output*). Copying cells needs no arithmetic by the owner, and every number keeps one definition. |
| D6 | **Cost and latency in section 6 are eval-run figures, labelled as such.** The rows are cost per query, cost per rules question, cost per action description, and latency p50/p95. No production latency is claimed. | These are the only measured figures the project produces (spec 009 *Metrics*, spec 010 D9). Production numbers would need a measurement that no spec defines; see *Future Considerations*. |
| D7 | **Guardrail values are written now from config, not slotted.** They are 500 characters, a 16 KiB body, 5 per minute and 50 per day per IP, a $1.00 daily cap, a 60 s turn timeout, `max_tokens` 100/400/700/300, and `max-instances=1`. The story **verifies each one against the built code and `infra/runtime-env.yaml`, and the code wins** if they differ. The same applies to every factual claim in the template, explicitly including "21 basic and special moves" (spec 002 D6), "a few hundred section chunks" (spec 007 D3; check against `data/index/chunks.json`), "at most three model calls" and the four `max_tokens` values (spec 006 D25). Row labels in the eval and cost tables are identical to spec 010's row labels, except the recall label, which uses the fixed `k`, so cells can be copied one to one. | These are configuration, not measurements, so they are available at implementation time. The spec's numbers come from specs 006 D25, 008 D7/D8/D10/D12/D13, 011 D1/D10, and code may have drifted during implementation. |
| D8 | **Model ids are not named outside the `eval-results` slot.** The architecture text describes routing per role (router, classifier, answer, embeddings, each from env). The concrete ids appear only in the eval section, filled from the report. | The tuning round (spec 010) may replace spec 007's provisional ids. Naming them now would either go stale or pre-empt the measurement. |
| D9 | **ADR links point to `docs/decisions.md` without a heading anchor**, for example `[ADR-012](docs/decisions.md)`. A test checks that every `ADR-NNN` in the README exists as a heading. | GitHub heading slugs for long ADR titles (colons, em dashes, slashes) are easy to get wrong, and a broken anchor fails silently. A file link plus a verified number is robust. |
| D10 | **The demo GIF lives at `docs/media/demo.gif` (new, owner-recorded)**: at most 20 s, at most 5 MB, recorded on the live URL after the production configuration is deployed. It shows one rules question with a citation click and one action description with "Roll the dice for me" ticked. | Recording needs the live deploy and the real models, so it is owner work. Keeping it under `docs/` keeps the root clean. 5 MB loads quickly on GitHub's README view. |
| D11 | **One new test file `backend/tests/test_readme.py`**, not an extension of `test_repository_compliance.py`. It checks structure, links, ADR references, placeholder hygiene and command drift. It never fails because slots are unfilled. | Spec 001 D6 puts repo-level tests in `backend/tests/`. A separate file keeps spec 001's file unchanged. A test that failed on unfilled slots would turn CI red until the owner gates finish, so slot completion is a grep in *Success Criteria* instead. |
| D12 | **No ADR is added.** | The README structure is dictated by handoff 11. Every decision it describes already has its own ADR. |
| D13 | **No "Status: under construction" line.** The visible `TODO-OWNER` slots are the status. | Two status signals could disagree. |

**Open risk:** the built code may differ from what specs 002–011 describe. D7 mitigates this: the story checks each factual claim against the code and corrects the prose, listing corrections in the PR description.

## Architecture / Design Overview

The change is documentation only. The README draws from the committed artifacts of earlier specs. Owner-gated values flow in later through the slots:

```
specs 001–011 (built)                        owner gates (later)
  docs/decisions.md ── ADR numbers ─┐          spec 011 step 8: docs/deploy.md "Live URL:" ──▶ demo-url
  infra/runtime-env.yaml, code ─────┤          live site + screen recorder ─────────────────▶ demo-gif
  Makefile (eval, compare) ─────────┼─▶ story 1: README.md (all prose, 5 slots)
  section 11 order / section 3 list ┘          spec 010 steps 6–7: evals/reports/comparisons/*.md
                                                   ├─ chosen column, quality rows ─────────▶ eval-results
                                                   ├─ block between comparison markers ───▶ eval-comparison
                                                   └─ chosen column, cost/latency rows ────▶ cost-latency
  README ## Development ──moved──▶ docs/development.md
  story 2: backend/tests/test_readme.py guards structure and links; grep "TODO-OWNER" = launch check
```

## Configuration

No configuration required. No env vars, flags or config files change.

## Data Model

Not applicable. The placeholder slot registry is in *Placeholder Slots and Owner Fill Procedure*.

## Impact on Existing Code

| Path | Action | Notes |
|------|--------|-------|
| `README.md` (new in 001; extended by 004, 007, 008, 009, 010, 011) | modify — **deliberate restructure (documentation only)** | Rewritten from *README Content*. Removed: the `> Status` line, `## Development` (moved, D4) and the `## License` heading (merged into `## Attribution`, D3). Kept: `## Attribution` with its heading text, `ATTRIBUTION.md` link and "unofficial" wording, so spec 001's `test_readme_has_attribution_section` passes unchanged. Affected callers: none. No test, spec or doc links to a README anchor other than the file itself. |
| `docs/development.md` (new) | create | The README's former `## Development` content, moved per D4. |
| `backend/tests/test_readme.py` (new) | create | *Testing*. |
| `docs/media/demo.gif` (new) | created at the owner gate | Not created by any story (D10). |
| `backend/tests/test_repository_compliance.py` (new in 001) | unchanged | Its README test still passes (D3). |
| `ATTRIBUTION.md`, `LICENSE` (new in 001), `docs/decisions.md`, `docs/architecture.md` (new in 001), `docs/deploy.md` (new in 011), `evals/README.md` (new in 009), `Makefile` (new in 009) | unchanged | Linked or read only. |

## README Content

The story writes `README.md` from the template below. Rules:
- Replace each `{{adr:<key>}}` per *ADR Reference Tokens*.
- Keep every `TODO-OWNER(...)` line and cell exactly as written.
- Verify every factual claim against the built code (D7).
- Wording may be tightened, but no sentence may be dropped that carries one of the facts in *Validation Rules*.

````markdown
# dw-companion

An unofficial [Dungeon World](https://github.com/Sagelt/Dungeon-World) rules site with an AI assistant for players and GMs at the table.

## The problem

Dungeon World is played fiction first: a player describes what their character does, and the table decides whether that triggers a move, which one, which stat to roll and what a 10+, 7–9 or 6- means. Mid-session that means someone leafing through the rulebook while everyone waits, or arguing from memory about what a move actually says. dw-companion puts the complete rules text online as linkable pages and adds an assistant that helps in two ways. It answers rules questions with links to the exact section it relies on. Given what a character does, it says which move is triggered (if any), why, and what each outcome means, and it can roll the dice. It is also a portfolio project in production-minded AI engineering. Every AI step is measured by evals, traced, budgeted, and kept away from the jobs that plain code does better.

## Live demo

<!-- TODO-OWNER(demo-url): replace the token below with the "Live URL:" value from docs/deploy.md as an autolink of the form <https://dw-companion-SUFFIX.run.app/> with the real value, then delete this comment. -->
**Live demo:** TODO-OWNER(demo-url). The rules are at `/`, the assistant at `/assistant/`.

<!-- TODO-OWNER(demo-gif): add docs/media/demo.gif (≤ 20 s, ≤ 5 MB, recorded on the live URL: one rules question with a citation click, one action with "Roll the dice for me"), replace the pending line below with
![A rules question answered with citation links, then an action description that shows a move card and a dice roll](docs/media/demo.gif)
and delete this comment. -->
_Demo GIF pending: TODO-OWNER(demo-gif)._

Things to try on `/assistant/`: "How does Hack and Slash work?", "I hold the door shut while the ghouls pound on it", "I tell the innkeeper my name". Tick "Roll the dice for me" to have the assistant roll.

The demo runs on a small budget: 5 messages per minute and 50 per day per visitor, and a global daily spending cap. When the cap is reached the assistant says so, and the rules pages keep working. Limits reset at 00:00 UTC.

## What the assistant does (and what it doesn't do with AI)

A router (a small LLM call with structured output) sorts every message into one of three intents.

- **Rules question.** Hybrid retrieval (embeddings plus BM25 keyword search) finds the most relevant rulebook sections. The answer model must answer only from those sections and cite them by section id, and every surviving citation becomes a link to the exact rules page.
- **Action description.** A classifier gets the description together with all 21 basic and special moves (the whole list every time, not a retrieved subset). It returns the move, a confidence and a rationale. "No move" is a first-class answer, because in Dungeon World plenty of actions trigger nothing. When the classifier is not confident, the assistant asks one clarifying question instead of guessing. Otherwise it explains why the trigger matches and shows a move card with the stat and the outcome bands, and it rolls if asked.
- **Anything else** gets a short fixed reply saying what the assistant can do, with no further model calls.

### Deliberately not AI

| Job | Done by | Why |
|---|---|---|
| Rolling dice | [`backend/domain/dice.py`](backend/domain/dice.py): `2d6 + modifier`, banded into 10+ / 7–9 / 6-. The modifier comes from what the user typed, never from model output. | A model must never invent a result. Code is exact, free, and unit-tested with seeded randomness. |
| Outcome text | Quoted verbatim from the structured data parsed from the rulebook, and shown on the move card, never in the model's prose. When a move does not state a miss, the card says "Not stated by this move." | The rulebook is the authority, and paraphrased outcomes drift. Most moves leave the miss to the GM, so the assistant does not invent one. |
| Validating citations | [`backend/graph/citations.py`](backend/graph/citations.py): any cited section that was not actually retrieved is stripped and the event is traced. If no valid citation remains, the reply is "I couldn't find this in the rules." plus links to the closest sections. | A hallucinated citation can never reach the user. This is the main anti-hallucination signal, and the evals measure it as citation validity. |
| Choosing the stat to roll | Taken from the move's data, overriding the classifier when they disagree. | Structured data beats model output wherever both exist. |
| Clarifying questions, "no move" and out-of-scope replies | Fixed templates. | Zero cost and latency, and fully testable. |

## Architecture

```
Sagelt/Dungeon-World XML (git submodule, pinned commit)
        │ ingestion/ (Python, offline)
        ▼
data/normalized/*.json (sections, moves, classes; committed)
        │                                       │
        │ index build (offline, embeddings)     │ Astro build
        ▼                                       ▼
data/index/ (vectors + chunks; committed)      site/dist/ (rules pages + /assistant/ widget)
        └──────────────────┬────────────────────┘
                           ▼ one container image
             Cloud Run, single instance
             ├─ /            static rules site
             ├─ GET  /api/health
             └─ POST /api/chat ─▶ guardrails ─▶ LangGraph assistant ─▶ OpenRouter (LLMs, embeddings)
                                                        └─▶ Langfuse (model, tokens, cost, latency, intent)
```

```
router ─┬─ rules_question ─────▶ retrieve ─▶ answer_with_citations ─▶ citation_validator ─▶ cited answer | "couldn't find this"
        ├─ action_description ─▶ classify_move ─┬─ low confidence ─▶ clarifying question (template)
        │                                       ├─ no_move ────────▶ "No move is triggered" + rationale
        │                                       └─ move ───────────▶ explain ─▶ [roll ─▶ outcome]
        └─ out_of_scope ───────▶ fixed reply
```

1. **Request.** The widget posts the message to `/api/chat` on the same origin. Before any model call, the API checks the size, the input and the spend cap, then the rate limit. It then streams progress events (Server-Sent Events) while the graph runs, and sends the validated reply at the end. Tokens are not streamed, because the answer can only be shown after its citations are checked.
2. **Router.** The router picks the intent. It runs on a small model with a JSON schema at temperature 0.
3. **Rules branch.** It retrieves the top sections, generates an answer with inline section-id citations, then the deterministic validator keeps only citations from the retrieved set.
4. **Move branch.** It classifies against the full move list, then either asks for clarification, answers "no move", or explains the move. An optional roll and outcome come from domain code.
5. **Every node is traced** in Langfuse, with model, tokens, cost, latency and intent, under a random session id. Any provider failure or malformed model output ends the turn with a fixed error reply.
6. **Ports and adapters.** `backend/domain` holds pure types and dice. `backend/ports` holds the interfaces, `backend/adapters` the OpenRouter, retrieval, Langfuse and JSON implementations, `backend/graph` the LangGraph nodes and `backend/api` FastAPI. The whole graph is tested against fakes, so CI never calls a paid API. Each role (router, classifier, answer, embeddings) reads its model id from the environment.

Node-by-node details are in [`docs/architecture.md`](docs/architecture.md). To run everything locally, see [`docs/development.md`](docs/development.md).

## Evaluation

Three hand-labelled datasets live in [`evals/datasets/`](evals/datasets/): router messages (including mixed and adversarial ones), rules questions (including questions the rules do not answer), and action descriptions covering every basic and special move, ambiguous pairs and actions that trigger no move. The labels are written or reviewed by the project owner, an experienced GM. They are never generated by the model under test, and the runner refuses to run on any row not marked as reviewed. See [`evals/README.md`](evals/README.md).

### Results

<!-- TODO-OWNER(eval-results): from the committed comparison file (evals/reports/comparisons/), copy the chosen configuration's column and the Cases column for these rows. Replace the Configuration line with: Configuration `<name>`: router `<id>`, classifier `<id>`, answer `<id>`, embeddings `<id>` (from the report JSON "config.models"), report [`evals/reports/<file>.md`](evals/reports/<file>.md), run on <YYYY-MM-DD>. Then delete this comment. -->
Configuration: TODO-OWNER(eval-results).

| Metric | What it measures | Cases | Result |
|---|---|---|---|
| Router accuracy | Messages sent to the right branch: rules question, action or out of scope. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Retrieval recall@6 | Share of the expected rulebook sections found among the 6 retrieved. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Citation validity | Citations that point to a section actually retrieved. Invalid ones are stripped before the user sees them. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Key-fact coverage | Required facts present in the answer, scored by an LLM judge with a written rubric. The judge model differs from the answer model. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Correct refusals | Questions the rules do not answer where the assistant said so instead of inventing an answer. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Move accuracy | Actions classified as the expected move, or as an accepted alternative for genuinely ambiguous cases. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| `no_move` precision | When the assistant says "no move", how often that is right. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| `no_move` recall | Of the actions that trigger no move, how many it recognised. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |
| Clarification rate | Actions where it asked a clarifying question instead of answering. | TODO-OWNER(eval-results) | TODO-OWNER(eval-results) |

### Configuration comparison

Measure before you trust: the tuning round runs configurations on the same reviewed datasets, with the same judge and on the same commit. It then decides with a rule written before seeing the numbers. The cheaper configuration is kept unless the more expensive one meets all three conditions. First, its targeted metric improves by more than two cases' worth. Second, on that metric's dataset, the cases it alone gets right outnumber the cases only the cheaper one gets right by at least 3. Third, no other headline rate regresses by more than two cases' worth. The owner may override the outcome only with a recorded reason. The full rule is in [`evals/README.md`](evals/README.md#tuning-round).

<!-- TODO-OWNER(eval-comparison): paste the block between the comparison-table:start and comparison-table:end marker comments from the committed comparison file, both marker comments included. Below it write: "Chosen: `<config>`. <one sentence: the reason, including whether the decision rule was met>. Full comparison: [`evals/reports/comparisons/<file>.md`](evals/reports/comparisons/<file>.md); decision record: [ADR-<NNN>](docs/decisions.md)." Then delete this comment and the pending line. -->
_Comparison pending: TODO-OWNER(eval-comparison). It will compare the baseline with a larger-classifier candidate, showing accuracy deltas next to cost and latency deltas._

### Reproduce

With an OpenRouter key and Langfuse keys in `.env` (see [`docs/development.md`](docs/development.md)):

```
make eval                                         # every dataset, baseline config, default budget guard
make eval CONFIG=<name> DATASET=router BUDGET=1.50
make compare REPORTS="evals/reports/<reference>.json evals/reports/<candidate>.json"
```

The runner estimates the cost from live prices before any paid call and aborts above the budget. Each run writes a JSON report and a Markdown summary to `evals/reports/` and is traced in Langfuse with its configuration. The GitHub workflow "Evals" runs the same command, but only on manual dispatch.

## Cost, latency and guardrails

<!-- TODO-OWNER(cost-latency): from the same committed comparison file, copy the chosen configuration's values for these rows and replace the Source line with: Source: [`evals/reports/comparisons/<file>.md`](evals/reports/comparisons/<file>.md), configuration `<name>`. Then delete this comment. -->
Source: TODO-OWNER(cost-latency).

| Measure | Value |
|---|---|
| Cost per query | TODO-OWNER(cost-latency) |
| Cost per rules question | TODO-OWNER(cost-latency) |
| Cost per action description | TODO-OWNER(cost-latency) |
| Latency p50 | TODO-OWNER(cost-latency) |
| Latency p95 | TODO-OWNER(cost-latency) |

Costs are the ones the provider reports per call (OpenRouter `usage.cost`), summed per turn and averaged over all eval cases. The eval judge is excluded. An out-of-scope message costs one router call. Latencies are whole-turn wall-clock times from the eval runner, which runs cases one at a time. They are not production measurements.

Guardrails, all enforced before any model call unless noted:

- **Input limits.** Messages are at most 500 characters and request bodies at most 16 KiB. Validation is strict and rejects unknown fields.
- **Rate limit per visitor.** 5 messages per minute and 50 per day. Visitors are keyed by a salted hash of the IP and never by the raw address.
- **Daily spend cap.** A global $1.00 per UTC day, counted from provider-reported cost. Past the cap the API answers "The demo budget is used up for today. Please come back tomorrow. The rules pages still work in the meantime."
- **Bounded calls.** Every model call has `max_tokens` (router 100, classifier 400, answer 700, explanation 300), and each turn times out after 60 s. A turn makes at most three model calls.
- **One instance.** Limits and the spend counter live in memory. The service runs with `max-instances=1` so there is one ledger. The counters reset on deploy or restart, so the hard bounds are a credit limit on the OpenRouter key and a GCP budget alert ([{{adr:api}}](docs/decisions.md), [{{adr:deploy}}](docs/decisions.md)).
- **Prompt injection, handled proportionately.** The assistant has no tools and no sensitive data. User text is delimited and declared as data in every prompt, off-topic requests get a fixed reply, and the widget renders model text as plain text with links built only from known section ids.
- **Privacy.** IPs never reach traces or logs, and sessions use a random id per page load. Messages and answers are sent to Langfuse for tracing.
- **Evals.** The runner has its own budget guard (default $3 per run). Pull-request CI calls no paid API.

## Trade-offs and decisions

Every decision is logged in [`docs/decisions.md`](docs/decisions.md). The main ones:

- **Deterministic where it matters.** Dice, outcome text, the rolled stat and citation validation are plain code. The model routes, classifies and writes prose. The assistant cannot improvise a miss that a move does not state, and in exchange its correctness can be unit-tested ([{{adr:graph}}](docs/decisions.md), [{{adr:domain}}](docs/decisions.md)).
- **The source text wins.** Where the project brief and the rulebook disagreed (most moves state no miss), the book was followed. The source is a pinned submodule and is never hand-copied ([{{adr:outcome-bands}}](docs/decisions.md), [{{adr:submodule}}](docs/decisions.md)).
- **No managed vector database.** One rulebook is a few hundred section chunks. A NumPy matrix plus in-house BM25, fused with reciprocal rank fusion, is built offline, committed and baked into the image. There is no server and no bill, but changing the index needs a rebuild and a deploy. Keyword search is there because game terms like "Hack and Slash" or "hold" are matched better by exact words than by embeddings ([{{adr:retrieval}}](docs/decisions.md)).
- **One gateway for models.** OpenRouter serves both chat and embeddings with one key and reports the cost of every call. Model ids come from the environment, so swapping a model is a configuration change ([{{adr:provider}}](docs/decisions.md)).
- **Model choice by measurement.** See [Evaluation](#evaluation).
- **Progress streaming, not token streaming.** The answer is shown only after its citations are validated, so a stripped citation is never flashed on screen. The cost is perceived latency ([{{adr:api}}](docs/decisions.md)).
- **In-memory limits on a single always-on instance.** There is no Redis or Firestore. `max-instances=1` keeps one spend ledger, and the default `min-instances=1` stops scale-to-zero from resetting the cap, at the price of an idle instance ([{{adr:deploy}}](docs/decisions.md)).
- **One container, one origin.** The API serves the static site, so the widget calls a relative `/api/chat` with no CORS and no build-time URL ([{{adr:widget}}](docs/decisions.md), [{{adr:deploy}}](docs/decisions.md)).
- **Static site with stable URLs.** Page URLs derive from section ids, never from titles, because citations depend on them ([{{adr:site}}](docs/decisions.md), [{{adr:ingestion}}](docs/decisions.md)).
- **Tracing never blocks a reply.** Langfuse export is asynchronous and failures are swallowed ([{{adr:tracing}}](docs/decisions.md)).
- **Humans label, CI doesn't spend.** Eval labels are owner-reviewed, the judge model differs from the answer model, and evals run only on manual dispatch with a budget guard ([{{adr:evals}}](docs/decisions.md), [{{adr:ci}}](docs/decisions.md)).
- **Single-turn conversations.** There is no memory between messages, so answering a clarifying question means restating the action. That keeps prompts and evals simple ([{{adr:graph}}](docs/decisions.md)).

## What I'd do next

These were deliberately left out of scope:

- **Class moves in the classifier.** They are already searchable through rules answers. Classifying them needs to know which class the character is, and that is character state the assistant does not have.
- **Character sheets, persistent sessions, multiplayer and login.**
- **An "AI GM"** that runs a game. The assistant supports the people at the table and does not replace the GM.
- **Fine-tuning.** Prompting, routing and evals are enough at this scale.
- **Translation of the rules text.**
- **Answering in the user's language** (a nice-to-have). An Italian question would get an Italian answer, with citations still pointing to the English text, and a handful of eval cases would prove it works.

## Attribution

This project uses the text of **Dungeon World** by Sage LaTorra and Adam Koebel, from <https://github.com/Sagelt/Dungeon-World>, licensed under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The text has been adapted (parsed and reformatted). This project is **unofficial** and not endorsed by the authors. No art, logos or trade dress from the commercial book are used. The upstream licence also carries an SRD 5.1 notice (CC BY 4.0), which is reproduced with the full credits in [`ATTRIBUTION.md`](ATTRIBUTION.md).

Licensing is split: the **code** is [MIT](LICENSE), and the **rules text** remains CC BY 3.0 ([{{adr:licensing}}](docs/decisions.md)).
````

## ADR Reference Tokens

The story replaces each token with `ADR-NNN`, where `NNN` comes from the `## ADR-NNN: <title>` heading in `docs/decisions.md` whose title matches. If a title was worded differently when implemented, match it by the spec it came from and note this in the PR.

| Token | ADR title | From |
|-------|-----------|------|
| `{{adr:submodule}}` | Rules source pinned as git submodule | 001 (ADR-003) |
| `{{adr:licensing}}` | Licensing split: MIT code, CC BY 3.0 text, SRD 5.1 notice | 001 (ADR-004) |
| `{{adr:ci}}` | CI scope and the no-paid-API rule | 001 (ADR-006) |
| `{{adr:ingestion}}` | Ingestion: stdlib parser, chapter manifest, IDs, committed output as snapshot | 002 (ADR-007) |
| `{{adr:outcome-bands}}` | Outcome bands follow the source; extended stat vocabulary | 002 (ADR-008) |
| `{{adr:site}}` | Static site: Astro, URL contract, data loading and link check | 004 (ADR-009) |
| `{{adr:domain}}` | Domain layer — stdlib types, mirrored ingestion shapes, injected dice randomness | 005 |
| `{{adr:graph}}` | Assistant graph: LangGraph behind ports, deterministic citations, dice and outcomes | 006 |
| `{{adr:provider}}` | Model provider: OpenRouter for chat and embeddings | 007 |
| `{{adr:retrieval}}` | Retrieval: section chunks, NumPy + in-house BM25 hybrid, committed index | 007 |
| `{{adr:tracing}}` | Tracing: Langfuse adapter | 007 |
| `{{adr:api}}` | Chat API: SSE protocol, guardrails and in-memory limits | 008 |
| `{{adr:widget}}` | Chat widget: vanilla island on /assistant/, same-origin fetch | 008 |
| `{{adr:evals}}` | Evaluation harness | 009 |
| `{{adr:deploy}}` | Deploy: one Cloud Run service with min and max instances 1 | 011 |

The tuning-round ADR does not exist until spec 010's owner gate. Its number enters the README only through the `eval-comparison` slot.

## Development Guide (`docs/development.md`)

The story moves the README's `## Development` section, which holds content from specs 001, 004, 007, 008, 009, 010 and 011, into `docs/development.md` without changing its content. The only edits are these:
- The first line is `# Development`, and each `### ` subsection becomes `## `.
- Relative links are rewritten for the new location: `docs/decisions.md` → `decisions.md`, `docs/deploy.md` → `deploy.md`, `evals/README.md` → `../evals/README.md`, and so on. Every link must resolve (`test_development_doc_links_resolve`).
- A one-line intro under the title: "Commands for working on dw-companion locally. The project overview is in the [README](../README.md)."

## Placeholder Slots and Owner Fill Procedure

The convention is D1. The slot registry:

| Slot id | Where | Filled from | Available after |
|---------|-------|-------------|-----------------|
| `demo-url` | *Live demo*, one line | `Live URL:` line of `docs/deploy.md` | Spec 011 owner gate step 8 |
| `demo-gif` | *Live demo*, one line | `docs/media/demo.gif`, recorded by the owner (D10) | The live deploy runs the production configuration (after spec 010's step 8 and a redeploy, if the models changed) |
| `eval-results` | *Evaluation › Results*: Configuration line plus the Cases and Result cells | Committed comparison file `## Results`: the chosen config's column and Cases; models, report path and date from the chosen report JSON | Spec 010 owner gate step 6 |
| `eval-comparison` | *Evaluation › Configuration comparison*, block | The marker block of the same comparison file, plus the tuning ADR number | Spec 010 owner gate step 7 |
| `cost-latency` | *Cost, latency and guardrails*: Source line plus five cells | The same comparison file, the chosen config's cost and latency rows | Spec 010 owner gate step 6 |

**Fill rules (owner).**
1. Copy values exactly as spec 010's formatter printed them (`87.5%`, `$0.00125`, `1840 ms`), with no rounding or re-computation.
2. For each slot, replace every `TODO-OWNER(<id>)` occurrence and delete that slot's HTML comment.
3. Slots may be filled in any order and in separate commits (`docs(readme): fill <slot-id>`).
4. Launch check: `grep -n "TODO-OWNER" README.md` prints nothing, and `uv run pytest backend/tests/test_readme.py` passes. The link test then also proves that `docs/media/demo.gif` and the linked report files exist.
5. If a later tuning round changes the production configuration, refill `eval-results`, `eval-comparison` and `cost-latency` from the new comparison file.

## Validation Rules

These are enforced by `test_readme.py` unless marked *(review)*.

| Subject | Rule |
|---------|------|
| README headings | The `## ` headings outside fenced code are exactly, in order: `The problem`, `Live demo`, `What the assistant does (and what it doesn't do with AI)`, `Architecture`, `Evaluation`, `Cost, latency and guardrails`, `Trade-offs and decisions`, `What I'd do next`, `Attribution`. |
| `## Attribution` | Contains `Sage LaTorra`, `Adam Koebel`, `https://github.com/Sagelt/Dungeon-World`, `CC BY 3.0`, `adapted`, `unofficial`, `MIT`, `ATTRIBUTION.md`, `LICENSE`. |
| Relative links | Every `[..](target)` and `![..](target)` in `README.md` and `docs/development.md`, outside fenced code and HTML comments, whose target is not `http(s):`, `mailto:` or `#…`, resolves (fragment stripped) to an existing file or directory relative to the document. |
| ADR references | Every `ADR-\d{3}` in `README.md` has a matching `## ADR-NNN:` heading in `docs/decisions.md`. |
| Placeholders | `README.md` contains no `{{`, `}}` or `TBD`. Every `TODO` is the start of `TODO-OWNER(<id>)`, where `<id>` is one of the five slot ids. |
| HTML comments | In `README.md`, every `<!--` is closed by a `-->` before the next `<!--` (no nested or unclosed comments, which would leak instructions or hide content). |
| Commands | `README.md` contains `make eval` and `make compare`. `Makefile` defines targets `eval:` and `compare:`. |
| Development guide | `docs/development.md` starts with `# Development` and contains `## Running the assistant locally`, `## Running the API and chat widget locally`, `## Running evals`, `## Running the container and deploying` and `uv run pytest`. These are the `### ` subsection headings pinned verbatim by specs 007, 008, 009 and 011 (each spec's *Documentation* section: "add `### Running the assistant locally`", "`### Running the API and chat widget locally`", "`### Running evals`", "`### Running the container and deploying`"), promoted one level by D4. If a built heading differs, the built text wins and the test constant is updated to match, with a note in the PR. |
| Facts *(review)* | Section 3 names dice, outcome text and citation validation as deterministic code and says why. Section 6 states every guardrail in D7 with values that match the code. Section 8 lists every handoff 3 out-of-scope item plus the multilingual nice-to-have. |
| No fabrication *(review)* | Every unfilled slot holds only its token. No metric, cost, latency, URL or model id appears outside the filled slots. |

## Authorization & Security

There is no runtime surface. Documentation concerns:
- The README discloses that user messages are sent to Langfuse, and that IPs are never traced (handoff 7, spec 008 D17).
- No secret, project id or key appears in the README or `docs/development.md`. `GCP_PROJECT` stays a `<id>` placeholder, as in spec 011.
- The demo GIF must not show API keys, the Langfuse UI, a browser profile or personal data (*Owner Gate*).

## Testing

pytest, file `backend/tests/test_readme.py` (new), plain functions, `REPO_ROOT = Path(__file__).resolve().parents[2]` (spec 001 pattern). The tests are offline and read files only. Shared private helpers in the same file:
- `_strip_code_and_comments(text)` removes fenced code blocks (```` ``` ````) and `<!-- … -->` comments, including multi-line ones.
- `_section(text, heading)` returns the text between `## heading` and the next `## ` line.

Tests:
- `test_readme_sections_in_required_order`: the `## ` lines (prefix exactly `## `, outside fences) equal the *Validation Rules* list.
- `test_readme_attribution_states_licensing_split`: the *Validation Rules* `## Attribution` strings are all present in that section.
- `test_readme_relative_links_resolve`: per *Validation Rules*. The failure message lists every broken target.
- `test_development_doc_links_resolve`: the same check on `docs/development.md`.
- `test_readme_adr_references_exist`: per *Validation Rules*. Also asserts the README references at least one ADR, so the test cannot pass vacuously.
- `test_readme_has_no_unmanaged_placeholders`: no `{{`, `}}`, `TBD`. `re.findall(r"TODO(?!-OWNER\()", text) == []`. Every `TODO-OWNER\(([^)]*)\)` id is in `OWNER_SLOTS = frozenset({"demo-url", "demo-gif", "eval-results", "eval-comparison", "cost-latency"})`. This test passes both before and after the owner fills the slots.
- `test_readme_html_comments_are_well_formed`: per *Validation Rules*. The pasted comparison markers (`<!-- comparison-table:start -->`, `<!-- comparison-table:end -->`) satisfy it.
- `test_readme_reproduction_commands_match_makefile`: per *Validation Rules* (targets matched with `^eval:` / `^compare:` in multiline mode).
- `test_development_doc_has_moved_sections`: per *Validation Rules*.

The check logic sits in private pure functions that take text (and a base directory for links) and return a list of problems, for example `_broken_links(text, base_dir) -> list[str]`. The repo tests assert an empty list. These negative tests prove each guard fails on bad input, using inline strings and `tmp_path`, never the real README:
- `test_heading_check_rejects_wrong_order`: a text with `## Live demo` before `## The problem` is reported.
- `test_link_check_reports_missing_file`: `[x](missing.md)` in a `tmp_path` document is reported. `[x](https://example.com)`, `[x](#anchor)`, a link inside a fenced block and a link inside an HTML comment are not reported.
- `test_adr_check_reports_unknown_number`: `ADR-999` against a decisions text that has only `## ADR-001: …` is reported.
- `test_placeholder_check_rejects_bad_tokens`: `TODO-OWNER(demo_gif)`, a bare `TODO`, `TBD` and `{{adr:graph}}` are each reported. `TODO-OWNER(demo-url)` is not.
- `test_comment_check_rejects_nested_comment`: `<!-- a <!-- b --> c -->` is reported.

Edge cases these tests cover: a `TODO-OWNER(demo-gif)` typo such as `TODO-OWNER(demo_gif)` fails the placeholder test. A `docs/media/demo.gif` reference inside the HTML comment is not link-checked until the owner un-comments it. A link with a fragment (`evals/README.md#tuning-round`) is checked for the file only.

**Manual:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` and `uv run pytest` exit 0. Read the README rendered on GitHub (or with a Markdown preview) to check that tables and diagrams render.

## Suggested Story Breakdown

1. **[docs] README rewrite and development guide.** Create `docs/development.md` (move per *Development Guide*). Rewrite `README.md` from *README Content*, resolve every `{{adr:*}}`, and verify every factual claim against the code (D7), listing corrections in the PR. Verifiable: `grep -c "{{" README.md` = 0; `grep -c "TODO-OWNER" README.md` > 0; spec 001's `test_readme_has_attribution_section` is green. Depends on specs 001–011 being built.
2. **[tests] README guard tests.** `backend/tests/test_readme.py` with every test in *Testing*. Depends on 1.
3. **Owner gate (not a feature-builder story; story-creator emits it as an owner checklist).** Fill the five slots per *Placeholder Slots and Owner Fill Procedure* as each upstream gate completes, then run the launch check. Depends on 1, 2, spec 010's owner gate and spec 011's owner gate.

## Owner Gate

1. After spec 011 step 8, fill `demo-url`.
2. After spec 010 steps 6–7 (comparison and tuning ADR committed), fill `eval-results`, `eval-comparison` and `cost-latency` from the same comparison file.
3. Once the production configuration is deployed, record `docs/media/demo.gif` (D10, *Authorization & Security*) and fill `demo-gif`.
4. Launch check: `grep -n "TODO-OWNER" README.md` prints nothing, and `uv run pytest` passes.
5. Read the rendered README on GitHub once, top to bottom.

## Success Criteria

Implementer (stories 1–2):
- [ ] Every test in *Testing* exists and passes with `uv run pytest`. Spec 001's `test_readme_has_attribution_section` passes unmodified.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` exit 0.
- [ ] `README.md` has exactly the nine `## ` headings in handoff 11 order and contains no `{{`.
- [ ] `grep -o "TODO-OWNER([a-z-]*)" README.md | sort -u` lists exactly the five slot ids, and no visible slot line or table cell holds a metric, cost, latency, URL or model id value (only the token).
- [ ] `docs/development.md` exists, and `README.md` has no `## Development` and no `## License` heading.
- [ ] No file other than `README.md`, `docs/development.md` and `backend/tests/test_readme.py` changed.

Owner (milestone 11 acceptance):
- [ ] `grep -n "TODO-OWNER" README.md` prints nothing.
- [ ] `docs/media/demo.gif` is committed and at most 5 MB, and `test_readme_relative_links_resolve` passes.
- [ ] Every value in the README's results, comparison and cost/latency tables matches the committed comparison file cell for cell.

## Future Considerations

- Production cost and latency per query from Langfuse (live traffic), next to the eval-run figures (D6).
- A CI badge and a link to the latest "Evals" workflow run once the repository is public.
- Generating the README tables from the comparison file with a script, if tuning rounds become frequent (D5).
