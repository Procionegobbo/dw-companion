# 010 - Model tuning round

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 009, and only on reviewed/labelled datasets (see 009's critical rule).
**Reference:** `HANDOFF_dw-companion.md`, sections 4.2, 6.3, 10 (milestone 9).

## Scope

- Compare at least two model configurations on the same eval set (e.g. small vs large
  classifier model, or two retrieval `k` values) — accuracy delta vs cost delta.
- Pick one configuration and record the choice and the numbers that justified it in
  `docs/decisions.md`.
- This comparison is the "measure before you trust" evidence the README (spec 012) needs —
  produce it in a form (a small table) that can be pasted there directly.

## Out of scope

- Re-running or re-labelling the datasets themselves (spec 009's job).
