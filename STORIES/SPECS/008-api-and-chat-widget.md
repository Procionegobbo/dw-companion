# 008 - API and chat widget

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 004 (site exists), 007 (real graph), 003 (needs `astro-feature-builder` for
the widget's interactive island).
**Reference:** `HANDOFF_dw-companion.md`, sections 4.5, 7, 10 (milestone 7).

## Scope

**Backend** (`backend/api/`, implemented by `python-feature-builder`):

- `POST /api/chat` with SSE streaming; `GET /api/health`.
- Rate limiting per IP (a few requests per minute, a daily cap).
- Max input length — reject oversized messages before any LLM call.
- `max_tokens` on every model call (should already hold from spec 007, verify here too).
- Global daily spend cap: a counter checked before each request; over the cap, return a
  friendly "demo budget exhausted for today" message.
- No IP addresses in traces (random session ID — should already hold from spec 007).

**Frontend** (`site/`, implemented by `astro-feature-builder` from spec 003):

- Chat widget as an interactive island: streams the answer, renders citations as links to
  site anchors, shows the detected move as a small card (name, stat, outcome bands, dice
  result if rolled).

This spec spans two stacks — expect it to produce two stories against two different
feature-builders (`python-feature-builder` for the API, `astro-feature-builder` for the
widget), each closed out through its own `run-stage` review gate.

## Out of scope

- Evals (spec 009), deploy (spec 011).

## Acceptance

Chat widget works end-to-end against the local API, streaming, with citations and a move
card rendered, and the guardrails above are enforced and tested (rate limit, input length,
spend cap).
