# 001 - Bootstrap and tooling

**Status:** draft — to be expanded by spec-builder.
**Depends on:** none (first spec).
**Reference:** `HANDOFF_dw-companion.md`, sections 1, 2, 9, 10 (milestone 1), 12.

## Scope

Stand up the repository skeleton described in section 9 of the handoff (empty-but-wired, no
feature code yet):

- Folder layout: `docs/`, `vendor/dungeon-world/` (empty placeholder for the submodule),
  `ingestion/`, `data/normalized/`, `backend/{domain,ports,adapters,graph,api,tests}`,
  `evals/{datasets,reports}`, `site/`, `infra/`, `.github/workflows/`.
- Python toolchain: Python 3.12+, managed with `uv`, `ruff` (lint + format), a static type
  checker (pyright or mypy strict — pick one and record the choice and why in
  `docs/decisions.md`), `pytest`. Wire a single trivial passing test so CI has something to run.
- CI (GitHub Actions): lint, type-check, unit tests on every PR. No paid API calls anywhere
  in CI per section 6.4 — keep that constraint in mind even though evals come later.
- Git submodule: add `https://github.com/Sagelt/Dungeon-World` as a submodule at
  `vendor/dungeon-world/`, pinned to a specific commit (record the commit hash in
  `docs/decisions.md`). Do not hand-copy the text.
- Attribution and licensing per section 2 (binding, do not reinterpret): `ATTRIBUTION.md`
  crediting Sage LaTorra and Adam Koebel with links to the source repo and the CC BY 3.0
  license; `LICENSE` at repo root is MIT and covers code only; `README.md` gets a dedicated
  "Attribution" section (can be a stub here, filled properly in spec 012); state clearly
  that the project is unofficial and not endorsed by the authors; no art/logos/trade dress
  from the commercial book.
- Stub docs: `docs/decisions.md` (ADR log, starts with the entries this spec itself produces),
  `docs/source-notes.md` (empty stub — filled by spec 002), `docs/architecture.md` (empty
  stub — filled as the graph is built).
- `.env.example` documenting every environment variable introduced so far (likely none yet
  beyond placeholders for `MODEL_ROUTER` etc. — do not invent values, just note the pattern
  per section 12).

## Out of scope

- The actual ingestion parser (spec 002).
- The Astro application itself (spec 004) — TypeScript tooling here is limited to whatever
  is needed for an empty-but-wired `site/` to pass lint/typecheck in CI; do not scaffold
  Astro pages yet.
- Any backend logic beyond the toolchain wiring (specs 005+).

## Acceptance (from handoff milestone 1)

Done when CI is green on the empty-but-wired project, and `ATTRIBUTION.md` is complete.
