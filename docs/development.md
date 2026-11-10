# Development

Commands for working on dw-companion locally. The project overview is in the [README](../README.md).

Requirements: [uv](https://docs.astral.sh/uv/), Node 22.23.4 or newer 22.x, and a clone with
submodules (`git clone --recurse-submodules`, or `git submodule update --init` in an existing
clone).

Python (from the repo root):

    uv sync
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright
    uv run pytest

Site (from `site/`):

    npm ci
    npm run dev          # local dev server
    npm run lint
    npm run typecheck
    npm test
    npm run build
    npm run check-links  # after build

Copy `.env.example` to `.env` for local configuration. Design decisions are logged in
[`docs/decisions.md`](decisions.md).

## Running the assistant locally

Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`, the four `MODEL_*` values and,
optionally, the Langfuse keys (tracing stays disabled locally if you leave them empty).

Rebuild the retrieval index only after changing the rulebook data or the embedding model:

    uv run --env-file .env python -m backend.adapters.retrieval.build

Chat with the assistant from the command line:

    uv run --env-file .env python -m backend.chat "How does Hack and Slash work?"

Add `--roll --modifier 1` to roll the triggered move.

## Running the API and chat widget locally

Configure `.env` as in ["Running the assistant locally"](#running-the-assistant-locally)
above. The four `CHAT_*` keys (rate limits, daily spend cap, trusted proxy hops) are optional
and default to the values described in `.env.example`.

Start the API with a single worker (the rate limiter and spend ledger are in-memory, per
process):

    uv run --env-file .env uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log

Health check:

    curl http://127.0.0.1:8000/api/health

In `site/`, run `npm run dev` and open <http://localhost:4321/assistant/>. Requests to `/api`
are proxied to port 8000 by the Astro dev server.

## Running the container and deploying

Build the image:

    make image

Run it locally:

    docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local

then open <http://localhost:8080/>. The explicit `-e SITE_DIR=...` is needed because `.env`
(copied from `.env.example`) has an empty `SITE_DIR=`, which would otherwise override the
image's own default and serve only the API.

To serve the site without Docker, run `npm run build` in `site/`, then start the API as in
["Running the API and chat widget locally"](#running-the-api-and-chat-widget-locally) with
`SITE_DIR=site/dist`.

Deploying to Cloud Run is in [`docs/deploy.md`](deploy.md).

## Running evals

Dataset labels are owner-reviewed — see [`evals/README.md`](../evals/README.md) for the labelling
rule and the review procedure. No number from a run is meaningful before that review.

    make eval
    make eval CONFIG=<name> DATASET=router BUDGET=1.50

The manual "Evals" GitHub Actions workflow runs the same command, with repository secrets, on
demand (`workflow_dispatch`).

Compare two committed reports with `make compare REPORTS="<ref.json> <candidate.json>"`; the
procedure is in [`evals/README.md`](../evals/README.md).
