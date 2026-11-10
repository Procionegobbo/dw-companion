# Deploying dw-companion

Runbook for running dw-companion as a single public Cloud Run service (spec 011,
milestone 10). No script in this repository performs the owner account steps in
section 2 — those are manual, one-time actions in GCP's, OpenRouter's and Langfuse's
own consoles.

## Overview

```
BUILD (owner laptop, make deploy)                         RUN (Cloud Run, europe-west1, 1 instance)
Dockerfile                                                 https://dw-companion-…run.app
 ├ site   (node:22-slim, $BUILDPLATFORM)                     │ Google front end: TLS, X-Forwarded-For/Proto
 │   npm ci → npm run build → npm run check-links            ▼
 │   reads data/normalized/  →  site/dist/                 uvicorn (1 worker, no access log, proxy headers)
 ├ deps   (python:3.12-slim) uv sync --locked --no-dev       └ create_app()  (spec 008, + SITE_DIR mount)
 └ runtime (python:3.12-slim, USER app)                          /api/health, /api/chat  ── routes (first)
     /app/.venv  /app/backend  /app/data/{normalized,index}      /  ── StaticFiles(/app/site/dist, html=True)
     /app/site/dist   ENV SITE_DIR                               ▲ env: infra/runtime-env.yaml (MODEL_*, CHAT_*)
        │ docker buildx --platform linux/amd64 --push            ▲ secrets: Secret Manager → OPENROUTER_API_KEY,
        ▼                                                        │   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
Artifact Registry  europe-west1-docker.pkg.dev/<project>/dw-companion/app:<git sha>
        └──────────── gcloud run deploy (min=1, max=1, SA dw-companion-run) ─────────┘
                                   then infra/smoke.sh <url>
```

The service runs with `max-instances=1` and, by default, `min-instances=1`. This
overrides the project brief's `min-instances=0` default: spec 008 keeps the rate
limiter and daily spend cap in process memory, so there must be exactly one ledger,
not one per instance, and an always-cold instance would let the daily cap reset on
every cold start. `min-instances=1` bills for an idle instance around the clock —
see the ADR for the reasoning and the owner review item this creates.

## Owner account setup (manual, before the first deploy)

No script performs any of these steps.

1. **GCP project with billing.** Use a personal project, not one under an
   organization with domain-restricted sharing — org policy can block the
   `--allow-unauthenticated` flag this service needs (open risk d).
2. **GCP budget alert.** In the Cloud Console, Billing → Budgets & alerts, create a
   monthly budget on the project (e.g. 10 USD) with email alerts at 50%, 90% and
   100% of actual spend and 100% of forecast spend. An alert notifies; it does not
   stop spend.
3. **OpenRouter.** Create a dedicated production API key and set a credit limit on
   it, with auto top-up **off**, so the prepaid balance is the hard bound on LLM
   spend regardless of what the application does.
4. **Langfuse.** Create a cloud free-tier project and its public/secret key pair.
   Note the free tier's monthly observation allowance so tracing does not silently
   stop once it is exceeded.

## One-time GCP setup

Requires local `gcloud` credentials (`gcloud auth login`) with permission to create
resources in the target project.

```
gcloud auth login
make gcp-setup GCP_PROJECT=<id>
```

Re-running is safe — every step is skipped when it is already done. `make gcp-setup`
creates:

- the Run, Artifact Registry and Secret Manager APIs (enabled on the project),
- the `dw-companion` Artifact Registry Docker repository in `GCP_REGION` (default
  `europe-west1`), with the cleanup policy in `infra/ar-cleanup-policy.json` applied
  (keeps the 3 most recent image versions, deletes older ones after 1 day),
- the `dw-companion-run` runtime service account,
- the three Secret Manager secrets (`dw-companion-openrouter-api-key`,
  `dw-companion-langfuse-public-key`, `dw-companion-langfuse-secret-key`), each
  bound to `dw-companion-run` with `roles/secretmanager.secretAccessor` only.

It prompts for each secret's value with hidden input (`Value for <id> (input
hidden): `) the first time a secret has no enabled version. The value is read from
stdin and never echoed.

## Deploy

```
make deploy GCP_PROJECT=<id>
```

Requires a clean working tree (`git status --porcelain` empty) and a committed
`data/index/manifest.json`. Builds the image for `linux/amd64`, pushes it to
Artifact Registry tagged with `git rev-parse --short=12 HEAD`, and deploys it with
`gcloud run deploy` (1 vCPU, 512 MiB, concurrency 80, timeout 120 s, the committed
`infra/runtime-env.yaml` as plain env vars, and the three secrets as `:latest`
references). It then prints the live URL and runs `infra/smoke.sh` against it.

Pass `MIN_INSTANCES=0` to opt out of the always-on instance:

```
make deploy GCP_PROJECT=<id> MIN_INSTANCES=0
```

This prints a warning and lets the daily spend cap reset on every cold start (see
the ADR and open risk c); rely on the OpenRouter key's credit limit as the hard
bound if you choose this.

**Apple Silicon note:** the Python build stages run under QEMU emulation for
`linux/amd64`, so `make deploy` is slower on an Apple Silicon laptop than on an
`amd64` machine (open risk g). This affects build time only.

## Verify guardrails live

Performed once, right after the first deploy, against the live `https://` URL.
Every request below is a cheap out-of-scope turn (message `hello`), never a real
rules question.

1. **Rate limit and spoofing.** Send 6 valid requests within a minute, each with a
   different `X-Forwarded-For: 198.51.100.<n>` header. Requests 1–5 should get
   `200`, request 6 should get `429 rate_limited`. If request 6 also gets `200`,
   `CHAT_TRUSTED_PROXY_HOPS` is wrong (the key varies per request).
2. **Per visitor.** While still rate-limited, send one request from a different
   network (e.g. a phone on mobile data). It should get `200`. If it gets `429`
   instead, the key is a proxy address rather than the real client.
3. **Spend cap.** Temporarily lower the cap:
   `gcloud run services update dw-companion --region <region> --update-env-vars
   CHAT_DAILY_BUDGET_USD=0.0001`. The first request should get `200`, the second
   `503 budget_exhausted`. Then restore the committed configuration with
   `make deploy GCP_PROJECT=<id>`.
4. On any failure above, adjust `CHAT_TRUSTED_PROXY_HOPS` in
   `infra/runtime-env.yaml` (open risk b), redeploy, and repeat.

## Operations

- **Rollback.** List revisions, then shift all traffic to a previous one:

  ```
  gcloud run revisions list --service dw-companion --region <region>
  gcloud run services update-traffic dw-companion --region <region> \
    --to-revisions <revision>=100
  ```

- **Secret rotation.** Add a new version, then redeploy so the running instance
  picks it up (`:latest` is resolved at instance start):

  ```
  gcloud secrets versions add <secret-id> --data-file=-
  make deploy GCP_PROJECT=<id>
  ```

- **Changing models or limits.** Edit `infra/runtime-env.yaml`, commit, then
  `make deploy`. Changing `MODEL_EMBEDDINGS` also needs a retrieval index rebuild
  (`uv run --env-file .env python -m backend.adapters.retrieval.build`) before the
  next deploy, since the deployed index must match the configured model.
- **Counters reset on every deploy or restart** (open risk c). Worst-case daily LLM
  spend is `CHAT_DAILY_BUDGET_USD` × (1 + deploys and restarts that day), bounded in
  the end by the OpenRouter key's credit limit.
- **Memory.** 512 MiB is an estimate, not a measurement (open risk e). If Cloud Run
  logs an out-of-memory restart, raise `--memory` to `1Gi` in `infra/deploy.sh`.
- **CPU throttling.** Request-based billing throttles CPU once the SSE response
  ends, so Langfuse's background exporter may only flush a turn's spans on the next
  request or at shutdown (open risk a). If traces do not appear within a few
  minutes of a turn, the options are `--no-cpu-throttling` (instance-based billing,
  higher cost) or a per-turn flush in a later change.
- **Request logs.** Cloud Run's own request logs record client IPs in Cloud
  Logging; this is platform behaviour, not something the application does — the
  app's own access log is off and nothing is forwarded to Langfuse.

Live URL: https://dw-companion.procionegobbo.it
