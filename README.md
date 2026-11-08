# dw-companion

An unofficial Dungeon World rules site with an AI assistant for players and GMs at the table.

> Status: under construction.

## Development

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
[`docs/decisions.md`](docs/decisions.md).

### Running the assistant locally

Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`, the four `MODEL_*` values and,
optionally, the Langfuse keys (tracing stays disabled locally if you leave them empty).

Rebuild the retrieval index only after changing the rulebook data or the embedding model:

    uv run --env-file .env python -m backend.adapters.retrieval.build

Chat with the assistant from the command line:

    uv run --env-file .env python -m backend.chat "How does Hack and Slash work?"

Add `--roll --modifier 1` to roll the triggered move.

### Running the API and chat widget locally

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

## Attribution

This project uses the text of **Dungeon World** by Sage LaTorra and Adam Koebel, from
<https://github.com/Sagelt/Dungeon-World>, licensed under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The text has been adapted (parsed
and reformatted). This project is **unofficial** and not endorsed by the authors. See
[`ATTRIBUTION.md`](ATTRIBUTION.md) for full details.

## License

Code: [MIT](LICENSE). Rules text: CC BY 3.0, see [`ATTRIBUTION.md`](ATTRIBUTION.md).
