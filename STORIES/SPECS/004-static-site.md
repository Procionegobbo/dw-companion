# 004 - Static rules site

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 002 (needs `data/normalized/*.json`), 003 (needs `astro-feature-builder`).
**Reference:** `HANDOFF_dw-companion.md`, sections 4.5, 10 (milestone 3).

## Scope

Generate the static site from `data/normalized/*.json`:

- Astro, TypeScript strict mode. Keep it light — design is not the point, readability and
  working links are.
- A page for every section and every move, generated from the normalized data.
- Stable slugs: slugs derive from `section_id`/`move_id`, never from display titles that
  might change later — changing a slug breaks citations from the assistant.
- Footer with attribution and license, per section 2 (links to the CC BY 3.0 source and
  license, MIT notice for code, "unofficial" statement).
- Automated link check confirming every `section_id` and `move_id` resolves to a working URL.

## Out of scope

- The chat widget and its interactive island (spec 008) — this spec is the static pages only.
- Visual design beyond basic readability.

## Acceptance (from handoff milestone 3)

Done when every `section_id` and `move_id` resolves to a working URL, verified by an
automated link check.
