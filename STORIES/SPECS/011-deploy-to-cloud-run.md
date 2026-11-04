# 011 - Deploy to Cloud Run

**Status:** draft — to be expanded by spec-builder.
**Depends on:** 007 (real adapters), 008 (API+widget). Can proceed in parallel with 009/010.
**Reference:** `HANDOFF_dw-companion.md`, sections 7, 8, 10 (milestone 10).

## Scope

- Single container on Cloud Run serving both the API and the static site, `min-instances=0`.
- Secrets (LLM keys, Langfuse keys) via Secret Manager — never in the repo; `.env.example`
  stays the documentation of what's needed.
- Multi-stage Dockerfile: build ingestion output + index + static site, then a slim runtime
  image.
- `infra/` with a short deploy script or Makefile target (Terraform optional, not required).
- Billing budget alert set on the GCP project and on the LLM provider (OpenRouter) account —
  this is an account-level action outside the repo; call it out explicitly for the owner to
  do, do not assume an agent can configure third-party billing alerts.
- Langfuse cloud free tier.

## Out of scope

- README polish with the public URL (spec 012, which depends on this spec's output).

## Acceptance (from handoff milestone 10)

Public URL available, guardrails (rate limit, spend cap) verified live, budget guards in
place.
