# 005 - Domain types and dice resolution

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 001 (toolchain). Independent of 002/004 — can be built in parallel.
**Reference:** `HANDOFF_dw-companion.md`, sections 4.1, 10 (milestone 4).

## Scope

`backend/domain/`: pure types and logic, no I/O, no LLM imports, fully unit tested.

- Core types: `Move`, `Section`, `Outcome` (matching the shapes produced by the ingestion
  pipeline in spec 002, even though this spec has no runtime dependency on it).
- Deterministic dice resolution: `2d6 + modifier` → `10+ | 7-9 | 6-` band. The LLM never
  invents a roll (enforced later in spec 006/008, but the primitive lives here).
- Seeded RNG so tests are deterministic.
- Full unit test coverage for the dice bands (including boundary values) and the type
  invariants.

## Out of scope

- Anything that touches a port, adapter, or the graph (specs 006+) — this layer has no I/O.
- The "roll" tool's exposure to the LLM/graph (spec 006 wires it in as a tool).
