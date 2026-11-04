# Handoff: Dungeon World Companion (rules site + AI assistant)

Working name: `dw-companion` (rename freely).

This document is the full brief for the build. It is written for an agentic development pipeline: read it end to end before planning, then work milestone by milestone (section 10). Where a decision is marked **[decided]**, do not revisit it without asking the owner. Where it is marked **[open]**, pick a sensible default, document the choice in `docs/decisions.md`, and move on.

---

## 1. Purpose and audience

A public portfolio project on GitHub whose goal is to demonstrate **production-minded AI engineering**, not just "a chatbot over a PDF". The people reading the repo are hiring managers for AI Engineer / product engineer roles. They will look for:

- LLM features that actually ship: agents, classifiers, RAG, tool calling.
- **Evaluations with numbers**: quality, latency, cost, tracked and reproducible.
- Observability (tracing), model routing, token and cost awareness.
- Product sense: a clear problem, a clear user, and explicit choices about where AI is *not* used.
- Clean engineering: tests, CI, sensible architecture, a README that explains trade-offs.

Everything in this brief is in service of those signals. When in doubt between "more features" and "better measured / better explained", choose the latter.

**The product**: a website with the full Dungeon World rules, navigable and linkable, plus an assistant for players and GMs at the table. The assistant does two things:

1. Answers rules questions, citing the exact section of the rulebook (with a link that jumps to it on the site).
2. Given a description of what a character does in the fiction, identifies which move (if any) is triggered, explains why, and optionally rolls the dice and reports the outcome.

Point 2 is the differentiator. Dungeon World is "fiction first": players describe actions and the GM decides which move triggers. That is a real classification problem with a natural eval set, and it is what makes this more than a generic RAG demo.

---

## 2. Source material and licensing **[decided]**

- Source: the official Dungeon World text at **https://github.com/Sagelt/Dungeon-World**. The text is split by chapter in XML formatted for InDesign. Art is not included (we don't need it).
- License: **Creative Commons Attribution 3.0 Unported (CC BY 3.0)**. Read the repo's `LICENSE` file before starting and follow it.
- Obligations and rules for this project:
  - Credit the authors (Sage LaTorra and Adam Koebel) with a link to the source repo and to the license, in: `README.md` (dedicated "Attribution" section), a `NOTICE` or `ATTRIBUTION.md` file, and the site footer.
  - State that the text was adapted (parsed and reformatted) and that the project is **unofficial** and not endorsed by the authors.
  - Do not use any art, logos, or trade dress from the commercial book.
  - Our own code goes under a separate license (MIT unless the owner says otherwise). Keep a clear separation: the rules text is CC BY 3.0, the code is MIT. Say so in the README.
- Pull the source as a **git submodule or a pinned download** (record the commit hash). Do not hand-copy text.

---

## 3. Scope

### MVP (in scope)

1. **Ingestion pipeline**: parse the XML into a normalized, typed representation of the rulebook (sections, moves, classes), with stable IDs and anchors.
2. **Rules site**: static pages generated from the normalized data. Every section and every move has a stable anchor URL.
3. **Assistant** (chat widget on the site, backed by an API):
   - Router: classifies each message into `rules_question`, `action_description`, or `out_of_scope`.
   - Rules branch: retrieval + answer with citations that link to site anchors.
   - Move branch: move classification over **basic moves and special moves** + explanation + optional dice roll via a deterministic tool.
4. **Evals**: hand-labelled datasets, an eval runner, metrics, and a results report committed to the repo and summarized in the README.
5. **Tracing**: Langfuse on every graph node (model, tokens, cost, latency, intent).
6. **Model routing**: small/cheap model for routing and classification, larger model only where generation quality matters.
7. **Deploy**: Google Cloud Run, with rate limiting and a spend cap.
8. **CI**: GitHub Actions for lint, types, unit tests on every PR; evals on demand.

### Out of scope (deliberately; list these in the README under "What I'd do next")

- Class moves in the **classifier** (they remain searchable through RAG). Rationale: they depend on which class the character is, which needs character state.
- Character sheets, persistent sessions, multiplayer, login.
- An "AI GM" that runs a game.
- Fine-tuning.
- Translation of the rules text.

Nice to have, only after MVP is complete and measured: answering in the user's language (e.g. Italian question → Italian answer, citations still pointing to the English text), with a handful of eval cases to prove it works.

---

## 4. Architecture

```
                 ┌───────────────────────────────┐
  Sagelt XML ──▶ │ ingestion (Python, offline)   │──▶ data/normalized/*.json
                 └───────────────────────────────┘          │
                                │                           │
                                ▼                           ▼
                      index build (embeddings)      site generator (TS)
                                │                           │
                                ▼                           ▼
                        vector index artifact        static HTML pages
                                │                    + chat widget
                                ▼                           │
   ┌────────────────────── FastAPI (Cloud Run) ─────────────┘
   │  POST /api/chat (SSE streaming)   GET /api/health
   │
   │  LangGraph:
   │    router ──▶ rules_branch: retrieve ──▶ answer_with_citations ──▶ citation_validator
   │          └──▶ move_branch: classify_move ──▶ (clarify | explain) ──▶ [roll tool] ──▶ outcome
   │          └──▶ out_of_scope: short polite reply
   │
   └──▶ Langfuse (traces, cost, latency)
```

### 4.1 Backend structure **[decided: ports and adapters]**

Use a hexagonal layout (the owner works with this style in Go at work, and it pays off here because models and stores must be swappable and testable):

- `domain/`: pure types and logic. `Move`, `Section`, `Outcome`, dice resolution (`2d6 + modifier` → `10+ | 7-9 | 6-`). No I/O, no LLM imports. Fully unit tested.
- `ports/`: protocols for `LLMClient`, `Retriever`, `Tracer`, `RulebookRepository`.
- `adapters/`: concrete implementations (LLM provider SDK, vector store, Langfuse, JSON rulebook loader).
- `graph/`: LangGraph nodes and wiring. Nodes depend on ports, not adapters.
- `api/`: FastAPI app, request validation, rate limiting, SSE streaming.

Fakes for every port live in `tests/fakes/` so graph logic can be tested without network calls.

### 4.2 Models **[open on provider, decided on routing]**

- All model names come from config / env vars (`MODEL_ROUTER`, `MODEL_CLASSIFIER`, `MODEL_ANSWER`, `MODEL_EMBEDDINGS`). Never hardcode.
- Router and move classifier: small, fast, cheap model, structured output (JSON schema / tool call), temperature 0.
- Rules answers and move explanations: larger model.
- Record in `docs/decisions.md` which models were chosen and why, with the eval numbers that justified it. A small table comparing two or three model configurations on the same eval set is exactly the kind of evidence the README needs.

### 4.3 Retrieval

- Corpus is small (one rulebook). Chunk **by semantic section** from the normalized data, not by fixed token windows. Each chunk carries `section_id`, `title`, `chapter`, `anchor_url`, `type`.
- Moves are chunks of their own (one per move), never split.
- Hybrid retrieval: vector similarity + keyword (BM25). Rules questions often use exact game terms ("Hack and Slash", "Last Breath", "hold") that keyword search catches better than embeddings.
- **[decided]** Index is built offline and **baked into the container image** (e.g. Chroma persisted, LanceDB, or a FAISS/NumPy file). No managed vector DB: for this corpus it adds cost and ops for no benefit. Document this trade-off in the README.

### 4.4 Graph behavior details

**Router** output schema: `{ intent: "rules_question" | "action_description" | "out_of_scope", confidence: float }`. If an action description also contains a rules question, prefer `action_description` and let the explanation cover the rule.

**Rules branch**
- Retrieve top-k (start with k=6, tune via evals).
- Answer **only** from retrieved chunks. The prompt must require citations as section IDs.
- `citation_validator` node (deterministic code, not an LLM): every cited ID must exist in the retrieved set; invalid citations are stripped and the event is traced. If no valid citation remains, return "I couldn't find this in the rules" plus the closest sections as links. This is a key anti-hallucination signal; mention it in the README.
- Output rendered in the widget with clickable citation links to site anchors.

**Move branch**
- Input to the classifier: the user's description + the structured list of candidate moves (name, trigger text). Do not rely on retrieval to find the candidate moves: the list of basic + special moves is small enough to include entirely.
- Output schema: `{ move_id: string | "no_move", confidence: float, stat: "STR"|"DEX"|"CON"|"INT"|"WIS"|"CHA"|null, rationale: string, alternatives: [move_id] }`.
- **"no_move" is a first-class outcome.** In Dungeon World plenty of actions trigger no move. The eval set must include these cases.
- Low confidence (threshold tuned via evals) → ask one clarifying question instead of guessing (e.g. "Are you trying to avoid the fire or attack the dragon?").
- Explanation: why the trigger matches, which stat is rolled, what each outcome band means, quoting the move's outcomes from the structured data (not regenerated by the LLM).
- Dice: deterministic `roll` tool in `domain/`. The LLM never invents dice results. The user may supply their stat modifier; if not, the tool reports results per band without a total, or asks for the modifier. Seeded RNG in tests.

**Out of scope**: short reply saying what the assistant can do. No LLM call needed beyond the router.

### 4.5 Frontend **[open on framework]**

- TypeScript, strict mode. A static site generator such as Astro is a good fit (static pages + one interactive island for the chat). Keep it light; design is not the point, readability and working links are.
- Pages generated from `data/normalized/*.json`. Stable slugs: changing a slug breaks citations, so slugs derive from section IDs, not from display titles that might change.
- Chat widget: streams the answer, renders citations as links, shows the detected move as a small card (name, stat, outcome bands, dice result if rolled).
- Footer with attribution and license (section 2).

---

## 5. Ingestion details

- **First task: inspect the XML before writing the parser.** It is InDesign-flavored, so expect presentational tags, inconsistent nesting, and special characters. Write a short `docs/source-notes.md` describing the actual structure found.
- Parser must be tolerant and loud: unknown tags are logged and counted, not silently dropped. Fail the build if counts exceed a threshold.
- Output:
  - `sections.json`: `{ id, chapter, title, slug, parent_id, order, text_markdown }`
  - `moves.json`: `{ id, name, category: "basic"|"special"|"class", class: string|null, stat, trigger, outcomes: { strong_hit, weak_hit, miss }, body_markdown, section_id }`
  - `classes.json`: minimal, enough for site pages.
- Move extraction is the fragile part (outcome bands are prose, not fields). Validate with tests that assert known moves are parsed correctly (e.g. Hack and Slash, Defy Danger, Volley, Discern Realities, Last Breath). If some moves can't be parsed cleanly, a small hand-maintained override file is acceptable; document it.
- Snapshot tests on the normalized output so changes are visible in diffs.

---

## 6. Evaluations (the most important section for the audience)

### 6.1 Datasets (`evals/datasets/*.jsonl`)

- `router.jsonl`: ~40 messages with expected intent, including mixed and adversarial cases.
- `rules_qa.jsonl`: ~40 rules questions with `expected_section_ids` and a short list of `key_facts` the answer must contain. Include questions whose answer is *not* in the rules (expected behavior: say so).
- `move_classification.jsonl`: ~80 action descriptions with `expected_move_id` (or `no_move`) and `acceptable_alternatives` for genuinely ambiguous cases. Cover every basic and special move, multiple phrasings, ambiguous pairs (Defy Danger vs Hack and Slash, Spout Lore vs Discern Realities), and at least 15 `no_move` cases.

**Labelling rule [decided]**: labels are written or validated by the owner (an experienced GM). Agents may *draft* candidate cases, but every label must be reviewed by a human before entering the dataset, and the dataset must never be generated by the same model under test. Keep a `reviewed: true` field per row; the runner refuses unreviewed rows.

### 6.2 Metrics

- Router: accuracy, confusion matrix.
- Retrieval: recall@k against `expected_section_ids`.
- Rules answers: citation validity rate (deterministic), key-fact coverage (LLM-as-judge with an explicit rubric, judge model different from the answer model), correct refusal rate on unanswerable questions.
- Move classification: accuracy (counting `acceptable_alternatives` as correct), confusion matrix, `no_move` precision/recall, clarification rate.
- System: latency p50/p95 per intent, tokens and **cost per query** per intent.

### 6.3 Runner and reports

- `evals/run.py` (CLI): runs a dataset against a named config (model set + k + thresholds), writes `evals/reports/<date>-<config>.json` and a markdown summary.
- Every eval run is traced in Langfuse with the config as metadata (optionally also as Langfuse datasets/experiments).
- README contains a results table built from the latest committed report, plus one comparison between at least two configurations (e.g. small vs large classifier model: accuracy delta vs cost delta). That comparison is the "measure before you trust" story.

### 6.4 CI

- Every PR: ruff, type checking (pyright or mypy strict), pytest with fakes, frontend lint and typecheck, ingestion snapshot tests. No paid API calls.
- Evals: `workflow_dispatch` (manual) and optionally weekly, using repository secrets, with a hard budget guard in the runner (abort if estimated cost exceeds a threshold).

---

## 7. Guardrails, cost and safety

- Rate limiting per IP on `/api/chat` (e.g. a few requests per minute, a daily cap).
- Max input length; reject oversized messages before any LLM call.
- `max_tokens` on every model call.
- Global daily spend cap: a counter checked before each request; when exceeded, the API returns a friendly "demo budget exhausted for today" message. Also set a billing budget alert on the cloud project and on the LLM provider account.
- Prompt injection: the assistant has no sensitive tools or data, but the system prompt must still keep it on-topic, and the router handles off-topic requests. Note it in the README as a conscious, proportionate choice.
- No logging of IP addresses in traces; use a random session ID.

---

## 8. Deploy **[decided: GCP]**

- Single container on **Cloud Run** serving both the API and the static site (simplest), `min-instances=0`.
- Secrets (LLM keys, Langfuse keys) via Secret Manager.
- Multi-stage Dockerfile: build ingestion output + index + static site, then a slim runtime image.
- `infra/` with a short deploy script or Makefile target; Terraform is optional and not required for MVP.
- Langfuse: cloud free tier is fine.

---

## 9. Repository layout (suggested)

```
.
├── README.md
├── ATTRIBUTION.md
├── LICENSE                  # MIT, code only
├── docs/
│   ├── decisions.md         # ADR-style log of choices and trade-offs
│   ├── source-notes.md      # what the XML actually looks like
│   └── architecture.md      # diagram + node descriptions
├── vendor/dungeon-world/    # submodule, pinned commit
├── ingestion/               # Python: XML → data/normalized
├── data/normalized/
├── backend/
│   ├── domain/
│   ├── ports/
│   ├── adapters/
│   ├── graph/
│   ├── api/
│   └── tests/ (incl. fakes/)
├── evals/
│   ├── datasets/
│   ├── reports/
│   └── run.py
├── site/                    # TypeScript static site + chat widget
├── infra/
├── Dockerfile
└── .github/workflows/
```

---

## 10. Milestones and acceptance criteria

Work in this order. Each milestone ends with green CI and a short entry in `docs/decisions.md` if anything was decided.

1. **Bootstrap**: repo skeleton, tooling (Python 3.12+, `uv`, ruff, pyright/mypy, pytest; TS strict, lint), CI on PRs, submodule pinned, attribution files in place.
   *Done when*: CI green on an empty-but-wired project; `ATTRIBUTION.md` complete.
2. **Ingestion**: `docs/source-notes.md`, parser, normalized JSON, move extraction with tests on named moves, snapshot tests.
   *Done when*: all basic and special moves parse with trigger, stat and three outcome bands; unknown-tag count reported.
3. **Static site**: pages for all sections and moves, stable anchors, attribution footer.
   *Done when*: every `section_id` and `move_id` resolves to a working URL (automated link check).
4. **Domain + dice**: types, dice resolution, unit tests (seeded).
5. **Graph v1 with fakes**: router, both branches, citation validator, clarification path, all tested with fake ports.
6. **Real adapters**: LLM provider, retriever (hybrid), Langfuse tracer, index build step.
   *Done when*: end-to-end chat works locally and traces appear in Langfuse with tokens and cost.
7. **API + widget**: FastAPI with SSE, rate limit, input limits, budget cap; chat widget with citations and move card.
8. **Evals**: runner, metrics, first reports. **Pause here and ask the owner to review and label the datasets** before trusting any number.
9. **Tuning round**: compare at least two configurations, pick one, record why in `decisions.md`.
10. **Deploy** to Cloud Run with budget guards; public URL in README.
11. **README polish** (see section 11).

---

## 11. README requirements

In this order, concise:

1. One-paragraph problem statement: who it's for (players and GMs at the table) and what it solves.
2. Live demo link + a short GIF or screenshot.
3. What the assistant does (the two intents) and **what it deliberately doesn't do with AI** (dice, outcome text, citation validation are deterministic code, and why).
4. Architecture diagram and a short walk through the graph.
5. **Eval results table** + the configuration comparison + how to reproduce (`make eval`).
6. Cost and latency per query, and the guardrails in place.
7. Trade-offs and decisions (link to `docs/decisions.md`).
8. What I'd do next (the out-of-scope list).
9. Attribution and licensing (rules text CC BY 3.0, code MIT, unofficial).

---

## 12. Conventions for the pipeline

- Do **not** attribute changes to AI in code comments, commit messages, or PR descriptions.
- Conventional commits, small PRs, one milestone per branch where practical.
- No secrets in the repo; `.env.example` documents every variable.
- Prefer boring, well-known libraries. Every new dependency gets one line of justification in the PR description.
- When the source text and this brief disagree about game rules, the source text wins; flag the discrepancy.
- Stop and ask the owner when: a **[decided]** item seems wrong, eval labels need review (milestone 8), or anything would incur recurring cost beyond free tiers.
