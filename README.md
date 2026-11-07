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
