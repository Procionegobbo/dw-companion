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

## Attribution

This project uses the text of **Dungeon World** by Sage LaTorra and Adam Koebel, from
<https://github.com/Sagelt/Dungeon-World>, licensed under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The text has been adapted (parsed
and reformatted). This project is **unofficial** and not endorsed by the authors. See
[`ATTRIBUTION.md`](ATTRIBUTION.md) for full details.

## License

Code: [MIT](LICENSE). Rules text: CC BY 3.0, see [`ATTRIBUTION.md`](ATTRIBUTION.md).
