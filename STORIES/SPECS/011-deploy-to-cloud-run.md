# 011 - Deploy to Cloud Run

**Status:** spec — ready for story-creator.
**Depends on:** 001 (toolchain, `.env.example` rule, CI, `infra/`), 002 (committed `data/normalized/`), 004 (Astro build → `site/dist/`, `trailingSlash: "always"`, `build.format: "directory"`, `404.html`, `npm run check-links`), 007 (`Settings`, `build_runtime`, `ConfigError`, committed `data/index/`, env vars), 008 (`create_app`, `ApiSettings`, in-memory limits D9, `CHAT_TRUSTED_PROXY_HOPS` D11, open risks a/b), 009 (`Makefile`). Can proceed in parallel with 009/010 except for the `Makefile` edit, which needs 009's file to exist.
**Reference:** `HANDOFF_dw-companion.md` sections 3, 7, 8, 10 (milestone 10), 12.

## Feature Name & Description

**Deploy to Cloud Run.** Package the API and the static rules site into one container image and run it as a single public Cloud Run service, with LLM and Langfuse keys in Secret Manager and the guardrails from spec 008 actually effective in production. This is milestone 10: a public URL where anyone can read the rules and use the assistant, with spend bounded by code (daily cap, rate limit) and by account-level budget guards.

**Current state.** Nothing is implemented; specs 001–010 are approved but not built, so paths marked "(new in 00N)" come from those specs and do not exist on disk yet. Spec 008's widget calls the relative `/api/chat` and spec 008 D6 assumes "a single container serves both the site and the API", but spec 008 explicitly left serving the static site to this spec: `create_app` registers only `/api/health` and `/api/chat`. `infra/` holds only spec 001's `.gitkeep`. There is no Dockerfile, no deploy tooling and no GCP configuration.

**In scope.**
- Static site serving from `create_app` (opt-in via `SITE_DIR`), so one origin serves `/` and `/api/*`.
- Multi-stage `Dockerfile` and `.dockerignore`.
- `infra/` scripts: one-time GCP setup, deploy, smoke check; committed non-secret runtime config; Artifact Registry cleanup policy; `Makefile` targets.
- Cloud Run settings, including `max-instances=1` and `min-instances=1` (D1).
- A CI job that builds the image and smoke-tests it without secrets.
- Runbook `docs/deploy.md`, an ADR, a README pointer.
- An **owner gate** (not automatable): account-level budget alerts, OpenRouter key limit, Langfuse project, first deploy and live guardrail verification.

**Out of scope.**
- Configuring billing budgets, OpenRouter limits or Langfuse accounts from code (D13).
- A custom domain, CDN, Terraform, deploy-from-CI (D5, D6, *Future Considerations*).
- Persistent or shared rate-limit/spend state (spec 008 D9 future work).
- The README demo link and polish (spec 012). This spec records the URL in `docs/deploy.md`; spec 012 copies it.

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **`max-instances=1` and `min-instances=1`. This overrides handoff 8's `min-instances=0`.** `MIN_INSTANCES=0` remains available as an explicit deploy-time override, documented with its consequence. **Flagged discrepancy and owner review item #1** (recurring cost). | Spec 008 D9 keeps the rate limiter and spend ledger in process memory. `max-instances=1` is required so there is one ledger, not one per instance. `min-instances=0` would also undermine the daily cap: after ~15 idle minutes Cloud Run stops the instance, and the next request starts a fresh ledger at $0 spent, so a patient abuser could spend `CHAT_DAILY_BUDGET_USD` once per cold start. Handoff 8 (`min=0`, cheapest) and handoff 7 (a daily cap that holds) cannot both hold with spec 008's design; applying handoff 12's "the source wins; flag the discrepancy" rule by analogy, the approved, more specific spec 008 constraint wins over the brief's default, and the guardrail wins because it bounds real money, while `min=0` only saves idle cost. **Cost:** an idle min-instance (1 vCPU, 512 MiB, request-based billing) is billed at Cloud Run's idle rate, an unverified estimate of a few USD per month at list price (to be confirmed with the Cloud Run pricing calculator before the first deploy and on the first bill), likely above the free tier; handoff 12 says to stop and ask before recurring cost beyond free tiers, so this is an explicit owner review item. Choosing `MIN_INSTANCES=0` is acceptable if the owner relies on the OpenRouter key limit (D13) as the hard bound. Even with `min=1`, deploys and occasional platform restarts reset the counters (open risk c). |
| D2 | **The image copies the committed `data/normalized/` and `data/index/`; it does not re-run ingestion or the index build.** Only the static site is built inside Docker. **Flagged discrepancy** with handoff 8's wording "build ingestion output + index + static site". | Both artifacts are committed build outputs guarded by tests: spec 002 D13 (byte-for-byte snapshot test) and spec 007 D4 (index freshness test; "Spec 011's Dockerfile `COPY`s it"). Rebuilding the index needs `OPENROUTER_API_KEY` at build time, which would put a secret into the build (spec 007 D4 rejected this). Re-running ingestion needs the `vendor/` submodule in the build context, which spec 001 D10 wants kept out of the image. The handoff's intent (built offline, baked into the image, handoff 4.3) is preserved. |
| D3 | **`create_app` serves the static site when `SITE_DIR` is set**: after the API routes, it mounts Starlette `StaticFiles(directory=SITE_DIR, html=True)` at `/`. Unset (the default) keeps spec 008 behaviour exactly. The Dockerfile sets `SITE_DIR=/app/site/dist`. | Delivers spec 008 D6 (same-origin `/api/chat`, no CORS, no build-time API URL) and spec 004 D4 ("`StaticFiles(html=True)` serves and redirects slashless requests (spec 011)"). `html=True` serves `index.html` for directories, redirects `/x` to `/x/` when `/x/index.html` exists, and returns spec 004's `404.html` with status 404 for unknown paths. Routes registered before the mount win, so `/api/*` is unaffected. Opt-in keeps local dev (Astro dev server + proxy) and every spec 008 test unchanged. |
| D4 | **`CHAT_TRUSTED_PROXY_HOPS=1` in production, verified live**; uvicorn runs with `--proxy-headers --forwarded-allow-ips '*'`. | Spec 008 open risk (b) assumed Cloud Run's `X-Forwarded-For` ends with the client IP and required this spec to verify it; *Owner Gate* step 6 does so with three checks that distinguish "correct", "key is a proxy" and "key varies per request". Proxy headers make `request.url` use `https` from `X-Forwarded-Proto`, so the slash redirect's `Location` is `https://…`; only Google's front end can reach a Cloud Run container, so trusting its forwarded headers is the documented pattern. Spec 008's `client_ip` reads `X-Forwarded-For` itself with `hops ≥ 1`, so uvicorn's rewrite of `request.client` only affects the fallback path, which Cloud Run never takes (the header is always present). |
| D5 | **Build locally with `docker buildx build --platform linux/amd64 --push`, push to Artifact Registry, deploy with `gcloud run deploy`.** No Cloud Build, no deploy from GitHub Actions. The node stage runs on `$BUILDPLATFORM` (its output is architecture-independent), so on Apple Silicon only the Python stages are emulated. | One machine, one owner, manual milestone deploys. Cloud Build adds an API, IAM and a separate build environment; deploy-from-CI needs GCP credentials in GitHub (Workload Identity Federation) and a secret-bearing workflow, which spec 009's `SECRET_WORKFLOWS` rule would have to admit. Neither is needed for a demo. Cloud Run runs `linux/amd64` images. |
| D6 | **Bash scripts in `infra/` plus `Makefile` targets; no Terraform.** Scripts are idempotent, `set -euo pipefail`, and compatible with macOS's bash 3.2 (no associative arrays, `mapfile` or `${var,,}`). | Handoff 8: "a short deploy script or Makefile target; Terraform is optional". Spec 009 created the `Makefile`; spec 001 D16 deferred all `make` targets to the specs that need them. |
| D7 | **Names and region.** Region `europe-west1` (override with `GCP_REGION`). Cloud Run service `dw-companion`; Artifact Registry Docker repository `dw-companion`, image `app`, tag = `git rev-parse --short=12 HEAD`; runtime service account `dw-companion-run`. Secret ids `dw-companion-openrouter-api-key`, `dw-companion-langfuse-public-key`, `dw-companion-langfuse-secret-key`. `GCP_PROJECT` has no default and is never committed. | `europe-west1` is a tier-1 price region close to the owner and to Langfuse cloud's default EU region (`https://cloud.langfuse.com`, spec 007 D18). A commit-derived tag ties every revision to source; `deploy.sh`'s clean-tree check (*Validation Rules*) makes that true. Prefixed secret ids avoid collisions if the project is shared. |
| D8 | **Dedicated runtime service account with only `roles/secretmanager.secretAccessor` on the three secrets.** | The default compute service account has project Editor. Least privilege: the container needs to read three secrets and nothing else (logs to stdout need no role). |
| D9 | **Secrets.** All three Langfuse/OpenRouter values live in Secret Manager and are mounted as env vars with `--set-secrets NAME=<secret-id>:latest`. `setup.sh` creates each secret if missing and, if it has no enabled version, prompts for the value with hidden input and adds it from stdin. Rotation = add a version, then redeploy. | Handoff 8. `latest` is resolved at instance start, so a rotated key takes effect on the next deploy without editing config. Hidden prompt plus stdin keeps keys out of shell history, process lists and files. The Langfuse public key is not secret, but keeping the pair together matches handoff 8 and spec 007's both-or-neither rule. Usage is inside Secret Manager's free tier (3 active versions, a few accesses per instance start). |
| D10 | **Non-secret runtime config is committed in `infra/runtime-env.yaml`** and passed with `--env-vars-file`, which replaces all plain env vars on every deploy (declarative). Model ids are fixed to spec 007 D13's provisional values. After spec 010's owner gate chooses a configuration, the owner edits this file and redeploys (*Documentation*, `docs/deploy.md` Operations); no story waits on spec 010. | Spec 010 D4 / step 8: the chosen ids go "into the deploy env, which is spec 011's concern". Model ids and limits are not secrets; committing them makes the live configuration reviewable and reproducible. `.env.example` keeps empty values (spec 001 rule). |
| D11 | **Service resources:** 1 vCPU, 512 MiB, concurrency 80, request timeout 120 s, port 8080, request-based billing (`--cpu-throttling`), `--allow-unauthenticated`. | The workload is I/O-bound (LLM calls) on one asyncio worker; 80 concurrent streams is far above demo traffic. Python + NumPy + LangGraph + Langfuse + a ~3 MB index fit in 512 MiB (open risk e). 120 s exceeds spec 008's 60 s turn timeout. Request-based billing keeps the idle min-instance cheap (D1); its effect on background trace export is open risk a. Public, anonymous access per handoff 3. |
| D12 | **CI gains an `image` job**: `docker build`, run the container with placeholder (non-credential) env values, run `infra/smoke.sh` against it. No secrets, no GCP access, no paid call. | Proves on every PR that the Dockerfile builds, the runtime starts with the real composition root, and one origin serves the site and the API. Spec 001 D12 / handoff 6.4: no secrets in `ci.yml`; placeholder strings are not credentials and no LLM request is ever made (the smoke check's only POST is rejected with 422 before any LLM call, spec 008 D8). |
| D13 | **Account-level guards are owner actions and are not automated by any story**: GCP billing budget alert, OpenRouter credit limit on the production key (and keeping auto top-up off), Langfuse cloud project and keys, GCP project with billing. This spec documents them in `docs/deploy.md` and lists them in the *Owner Gate*; no script touches billing or third-party accounts. | Draft and handoff 7. Billing budgets need billing-account permissions and OpenRouter/Langfuse settings live in third-party web consoles; an agent has neither credential nor authority. A budget alert notifies, it does not cap; the OpenRouter key limit plus a prepaid balance without auto top-up is the hard bound on LLM spend. |
| D14 | **Public URL = Cloud Run's default `https://dw-companion-…run.app` URL**, recorded by the owner in `docs/deploy.md` (`Live URL:` line) after the first deploy. | Milestone 10 needs a public URL; a custom domain adds DNS ownership and setup for no acceptance value. Spec 012 copies the URL into the README. |
| D15 | **Artifact Registry cleanup policy keeps the 3 most recent image versions** and deletes older ones after 1 day. | Keeps storage within Artifact Registry's free 0.5 GB with ~300 MB images; 3 versions leave room for a rollback. |
| D16 | **Base images:** `python:3.12-slim` (both Python stages, one `ARG`), `node:22-slim`, `ghcr.io/astral-sh/uv:0.13.5` (`UV_VERSION=0.13.5`, the version installed on the owner's machine on 2026-11-05; an exact version, never `latest`; bumping it is a one-line change). The runtime runs as non-root user `app` (uid 10001). | Versions match `.python-version` (spec 001 D3) and `site/.nvmrc` (spec 001 D11), enforced by test. Both Python stages share a base so the copied virtualenv's interpreter path is identical. Tag pinning is enough for now; digest pinning is a *Future Consideration*. |
| D17 | **ADR number:** story 3 reads `docs/decisions.md`, takes the highest existing `## ADR-NNN` heading and uses NNN + 1 (zero-padded to three digits). | Spec 005 D16 … 008 D20 precedent. |

**Open risks.**
- (a) **Trace export under CPU throttling.** With request-based billing, CPU is throttled after the SSE response ends, so Langfuse's background exporter may send a turn's spans only during the next request or at shutdown (`Runtime.aclose` flushes, spec 007). Owner Gate step 7 checks traces arrive. If they do not within a few minutes, the options are `--no-cpu-throttling` (instance-based billing, higher cost) or a per-turn flush (a code change in a later spec).
- (b) **`X-Forwarded-For` layout** (spec 008 open risk b), resolved by Owner Gate step 6. If a check fails, change `CHAT_TRUSTED_PROXY_HOPS` in `infra/runtime-env.yaml` and redeploy; no code change.
- (c) **Counters reset on every new revision or restart.** Each `make deploy` (and the budget check in Owner Gate step 6) starts a fresh ledger. Worst-case daily LLM spend is `CHAT_DAILY_BUDGET_USD` × (1 + deploys and restarts that day) plus in-flight overshoot (spec 008 D12). The OpenRouter key limit (D13) is the hard bound. During a rollout the old and new instance briefly coexist, which is covered by the same bound.
- (d) **Org policy may block `allUsers`.** If the GCP project belongs to an organisation with domain-restricted sharing, `--allow-unauthenticated` fails; the runbook says to use a personal project without that constraint.
- (e) **Memory.** 512 MiB is estimated, not measured. If Cloud Run logs an out-of-memory restart, raise `--memory` to `1Gi` in `deploy.sh`.
- (f) **The committed index must exist** (spec 007 open risk f). Without `data/index/`, the image build fails at `COPY`, so the CI `image` job fails. Spec 007's owner step must be complete before this spec's story 2 merges.
- (g) **Emulated builds on Apple Silicon are slower** (Python stages under QEMU). This affects only build time.

## Architecture / Design Overview

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

`composition.py` resolves `data/` from `REPO_ROOT = Path(__file__).resolve().parents[1]` (spec 007), so the image mirrors the repo layout under `/app`. Uvicorn runs the lifespan startup (which builds the runtime and fails fast on bad config, spec 007 D23) before binding the port, so Cloud Run's default TCP startup probe only succeeds once the runtime is ready; a revision that fails to start never receives traffic, and the previous revision keeps serving.

## Configuration

**Environment variables.**

| Variable | Read by | Default | Meaning |
|----------|---------|---------|---------|
| `SITE_DIR` (new) | `backend/api/settings.py` | unset → no static site | Directory containing the built site (`index.html` at its root), served at `/` (D3). Set to `/app/site/dist` in the image. |
| `PORT` | container `CMD` (shell), not Python | `8080` | Set by Cloud Run. |
| `GCP_PROJECT` | `infra/setup.sh`, `infra/deploy.sh` | none (required) | Target project id. |
| `GCP_REGION` | `infra/setup.sh`, `infra/deploy.sh` | `europe-west1` | D7. |
| `MIN_INSTANCES` | `infra/deploy.sh` | `1` | `0` or `1` (D1). |

`PORT` and the `GCP_*`/`MIN_INSTANCES` variables are read by the container shell or the deploy scripts, not by application code, so they are not added to `.env.example`.

**`.env.example`** (modify, additive). Append at the end:

```dotenv
# Static site (spec 011). Directory with the built site (site/dist) to serve at /; leave empty to serve only the API.
SITE_DIR=
```

**`infra/runtime-env.yaml`** (new, exact content):

```yaml
# Non-secret runtime configuration for the Cloud Run service (spec 011).
# Applied with `gcloud run deploy --env-vars-file`, which replaces every plain env var on each deploy.
# OPENROUTER_API_KEY, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY come from Secret Manager, never from this file.
# Model ids: provisional (spec 007) until the spec 010 tuning ADR. MODEL_EMBEDDINGS must equal data/index/manifest.json.
MODEL_ROUTER: "openai/gpt-4.1-nano"
MODEL_CLASSIFIER: "openai/gpt-4.1-nano"
MODEL_ANSWER: "openai/gpt-4.1-mini"
MODEL_EMBEDDINGS: "openai/text-embedding-3-small"
LANGFUSE_BASE_URL: "https://cloud.langfuse.com"
CHAT_RATE_PER_MINUTE: "5"
CHAT_RATE_PER_DAY: "50"
CHAT_DAILY_BUDGET_USD: "1.00"
CHAT_TRUSTED_PROXY_HOPS: "1"
```

**`infra/ar-cleanup-policy.json`** (new, exact content):

```json
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}
]
```

**`.dockerignore`** (new, exact content). An allow-list, so `.env`, `.git`, `vendor/`, `STORIES/`, `evals/` and local build output can never enter the build context:

```
*
!pyproject.toml
!uv.lock
!.python-version
!backend/
backend/tests/
!data/normalized/
!data/index/
!site/
site/node_modules/
site/dist/
site/.astro/
**/__pycache__/
```

**`Makefile`** (new in 009; modify, additive). Append (recipe lines use a tab). Defaults live only in the scripts; empty exported values fall back to them:

```make
export GCP_PROJECT GCP_REGION MIN_INSTANCES

.PHONY: image gcp-setup deploy smoke
image:
	docker build -t dw-companion:local .

gcp-setup:
	infra/setup.sh

deploy:
	infra/deploy.sh

smoke:
	infra/smoke.sh "$(URL)"
```

## Data Model

No database or persisted entity. The only new typed field:

```python
# backend/api/settings.py   (modified, additive)
API_ENV_VARS: Final[tuple[str, ...]]   # spec 008's four names, then "SITE_DIR"
class ApiSettings:                     # frozen dataclass (spec 008)
    ...                                # existing four fields unchanged, same defaults
    site_dir: Path | None = None       # SITE_DIR, resolved with Path(value).resolve(); None when empty/unset
```

## Impact on Existing Code

Backend rows are for `python-feature-builder`. Nothing under `site/` changes: the Dockerfile only reads it.

| Path | Action | Notes |
|------|--------|-------|
| `backend/api/settings.py` (new in 008) | modify — **additive** | `site_dir` field, `SITE_DIR` appended to `API_ENV_VARS`, its validation joins the existing combined `ConfigError`. Unset gives `None`, so existing defaults and spec 008 tests are unchanged. |
| `backend/api/app.py` (new in 008) | modify — **additive** | Step 4 of spec 008's `create_app` wiring gains: after the routes and the `ApiError` handler, if `api_settings.site_dir` is not `None`, `app.mount("/", StaticFiles(directory=site_dir, html=True), name="site")`. Without `SITE_DIR` the app is identical to spec 008, so every spec 008 test passes unmodified. `starlette.staticfiles` is within spec 008's `test_api_imports_allow_list`. |
| `.env.example` (new in 001, extended 007/008) | modify — **additive** | `SITE_DIR=` with comment (*Configuration*). Still matches spec 001's `KEY=` pattern with unique keys; satisfies spec 008's `test_env_example_declares_api_settings` for the new name. |
| `Makefile` (new in 009, extended in 010) | modify — **additive** | Four targets (*Configuration*). `eval`/`compare` and their variables are unchanged; the new `export` line names only new variables. |
| `.github/workflows/ci.yml` (new in 001, extended 004) | modify — **additive** | New job `image` (*CI Image Job*). Existing jobs, triggers, permissions and concurrency unchanged; still no `secrets.` reference, so spec 001's `test_ci_workflows_reference_no_secrets` (as amended by spec 009) keeps passing. |
| `infra/.gitkeep` (new in 001) | **delete** | Placeholder; `infra/` now has real files. Nothing references it. |
| `Dockerfile` (new) | create | *Container Image*. |
| `.dockerignore` (new) | create | *Configuration*. |
| `infra/setup.sh` (new) | create | Executable. *Infra Scripts*. |
| `infra/deploy.sh` (new) | create | Executable. *Infra Scripts*. |
| `infra/smoke.sh` (new) | create | Executable. *Infra Scripts*. |
| `infra/runtime-env.yaml` (new) | create | *Configuration*. |
| `infra/ar-cleanup-policy.json` (new) | create | *Configuration*. |
| `backend/tests/test_api_settings.py` (new in 008) | modify — **additive** | Three cases (*Testing*). Existing cases unchanged. |
| `backend/tests/test_api_site.py` (new) | create | *Testing*. |
| `backend/tests/test_deploy_config.py` (new) | create | *Testing*. |
| `docs/deploy.md` (new) | create | *Documentation*. |
| `docs/decisions.md` (new in 001) | modify — **additive** | One ADR (*Documentation*). |
| `README.md` (new in 001) | modify — **additive** | One subsection under `## Development` (*Documentation*). `## Attribution` untouched. |
| `data/normalized/*`, `data/index/*` (new in 002/007) | read only | Copied into the image. |
| `site/**` (new in 001/004/008) | read only | Built inside the image. |

No breaking change: every modification is opt-in (`SITE_DIR`) or appends to a file.

## Container Image

**`Dockerfile`** (new). Exact content:

```dockerfile
# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:22-slim
ARG UV_VERSION=0.13.5

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Static site: architecture-independent output, so build on the host platform.
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS site
ENV ASTRO_TELEMETRY_DISABLED=1
WORKDIR /src/site
COPY site/package.json site/package-lock.json ./
RUN npm ci
COPY data/normalized/ /src/data/normalized/
COPY site/ ./
RUN npm run build && npm run check-links

# Python runtime dependencies only (no dev group).
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY backend/ /app/backend/
COPY data/normalized/ /app/data/normalized/
COPY data/index/ /app/data/index/
COPY --from=site /src/site/dist/ /app/site/dist/
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SITE_DIR=/app/site/dist
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.api.app:create_app --factory --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1 --no-access-log --proxy-headers --forwarded-allow-ips '*'"]
```

Notes: `exec` makes uvicorn PID 1, so Cloud Run's SIGTERM runs the lifespan shutdown and `Runtime.aclose` flushes traces. `--workers 1` and `--no-access-log` are required by spec 008 D9/D14/D17. Files are root-owned and read-only to `app`. `site/` is copied after `npm ci`, and `.dockerignore` excludes `site/node_modules/`, so dependencies are not overwritten. The site stage's relative `?raw` imports (spec 004 D5) resolve because `data/normalized/` sits at `/src/data/normalized/`, the same position relative to `site/` as in the repo.

## Static Site Serving

With `SITE_DIR` set, behaviour for requests that do not match an API route:

| Request | Response |
|---------|----------|
| `GET /`, `GET /rules/<id>/`, `GET /moves/<id>/`, `GET /assistant/`, assets | 200, the file (`index.html` for directories), Starlette's `ETag`/`Last-Modified` |
| `GET /moves/<id>` (no slash, directory exists) | 307, `Location` = same URL with `/` appended (`https://` behind Cloud Run, D4) |
| Unknown path, including unknown `/api/...` paths | 404 with the body of `SITE_DIR/404.html` (spec 004) |
| `HEAD` | as `GET` without body |
| Other methods on static paths | 405 |
| Path traversal (`..`, encoded) | never serves a file outside `SITE_DIR` (Starlette) |

`/api/health` and `/api/chat` keep spec 008 behaviour exactly because they are registered before the mount. No cache headers, compression or security headers are added (*Future Considerations*).

## Infra Scripts

All three: `#!/usr/bin/env bash`, `set -euo pipefail` on the next non-comment line, executable bit set, bash 3.2 compatible, run from the repo root (they `cd "$(dirname "$0")/.."` first). Inputs are read as `${VAR:-}` so unset and empty (as exported by `make`) behave the same under `set -u`. Errors go to stderr prefixed with the script name (`deploy: error: …`) and exit 1.

**`infra/setup.sh`** — one-time, idempotent GCP setup. Requires `GCP_PROJECT`; `GCP_REGION` defaults to `europe-west1`. Steps, each skipped when already done:
1. `gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project "$GCP_PROJECT"`.
2. If `gcloud artifacts repositories describe dw-companion --location "$GCP_REGION"` fails: create it with `--repository-format=docker --location "$GCP_REGION"`. Then always apply `gcloud artifacts repositories set-cleanup-policies dw-companion --location "$GCP_REGION" --policy=infra/ar-cleanup-policy.json --no-dry-run`.
3. If `dw-companion-run@$GCP_PROJECT.iam.gserviceaccount.com` does not exist: `gcloud iam service-accounts create dw-companion-run --display-name "dw-companion Cloud Run runtime"`.
4. For each secret id in D7: create it if missing (`gcloud secrets create <id> --replication-policy=automatic`). If it has no enabled version (`gcloud secrets versions list <id> --filter=state:enabled --limit=1 --format='value(name)'` is empty), prompt `Value for <id> (input hidden): ` with `read -rs`, refuse an empty value, and add it with `printf '%s' "$value" | gcloud secrets versions add <id> --data-file=-`. Then `gcloud secrets add-iam-policy-binding <id> --member "serviceAccount:dw-companion-run@$GCP_PROJECT.iam.gserviceaccount.com" --role roles/secretmanager.secretAccessor`.
5. `gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev" --quiet`.
6. Print `setup: done` and the next command (`make deploy GCP_PROJECT=<id>`).

Every `gcloud` call passes `--project "$GCP_PROJECT"`. The script never echoes a secret value.

**`infra/deploy.sh`** — build, push, deploy, smoke.
1. Validate inputs (*Validation Rules*): `GCP_PROJECT` set and well-formed, `GCP_REGION`, `MIN_INSTANCES` ∈ {0, 1}; `gcloud`, `docker`, `git`, `curl` on `PATH`; `git status --porcelain` empty (otherwise `deploy: error: working tree is not clean; commit or stash first`); `data/index/manifest.json` exists. If `MIN_INSTANCES=0`, print a warning: `deploy: warning: MIN_INSTANCES=0 lets the daily spend cap reset on every cold start (see docs/deploy.md)`.
2. `TAG=$(git rev-parse --short=12 HEAD)`; `IMAGE="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/dw-companion/app:$TAG"`.
3. `docker buildx build --platform linux/amd64 -t "$IMAGE" --push .`
4. Deploy with exactly these flags:
   ```
   gcloud run deploy dw-companion --project "$GCP_PROJECT" --region "$GCP_REGION" --image "$IMAGE" \
     --service-account "dw-companion-run@$GCP_PROJECT.iam.gserviceaccount.com" \
     --allow-unauthenticated --port=8080 --cpu=1 --memory=512Mi --concurrency=80 --timeout=120 \
     --cpu-throttling --min-instances="$MIN_INSTANCES" --max-instances=1 \
     --env-vars-file=infra/runtime-env.yaml \
     --set-secrets=OPENROUTER_API_KEY=dw-companion-openrouter-api-key:latest,LANGFUSE_PUBLIC_KEY=dw-companion-langfuse-public-key:latest,LANGFUSE_SECRET_KEY=dw-companion-langfuse-secret-key:latest \
     --quiet
   ```
5. `URL=$(gcloud run services describe dw-companion --project "$GCP_PROJECT" --region "$GCP_REGION" --format='value(status.url)')`, print `deploy: live at $URL (image $TAG)`, then `infra/smoke.sh "$URL"`. A smoke failure exits 1 and prints the rollback command from `docs/deploy.md`.

**`infra/smoke.sh BASE_URL`** — cost-free checks against a running instance (no successful `/api/chat` call). Strips one trailing `/` from `BASE_URL`. First polls `GET /api/health` up to 30 times, 2 s apart, until 200. Then runs every check, printing `smoke: ok <name>` or `smoke: FAIL <name>: <detail>`, and exits 1 if any failed, else prints `smoke: all <n> checks passed`.

| Name | Request | Pass when |
|------|---------|-----------|
| `health` | `GET /api/health` | 200 and body matches the extended regex `"status"[[:space:]]*:[[:space:]]*"ok"` (independent of serializer spacing; no `jq` dependency on the owner's machine) |
| `home` | `GET /` | 200, `Content-Type` starts with `text/html`, body contains `href="/assistant/"` |
| `assistant` | `GET /assistant/` | 200 and body contains `id="chat-form"` |
| `move-page` | `GET /moves/hack-and-slash/` | 200 |
| `slash-redirect` | `GET /moves/hack-and-slash` (no redirect following) | 307 and `Location` ends with `/moves/hack-and-slash/`; if `BASE_URL` starts with `https://`, `Location` also starts with `https://` |
| `not-found` | `GET /no-such-page/` | 404 and `Content-Type` starts with `text/html` |
| `chat-rejects-invalid` | `POST /api/chat`, `Content-Type: application/json`, body `{}` | 422 and body contains `"invalid_request"` (no LLM call, does not count against the rate limit, spec 008 D8) |

## CI Image Job

Appended to `.github/workflows/ci.yml` as job `image` (`runs-on: ubuntu-latest`, `timeout-minutes: 20`, no `needs`, inherits top-level `permissions: contents: read`). Steps:
1. `actions/checkout@v7` (no submodules: the image never needs `vendor/`).
2. `docker build -t dw-companion:ci .`
3. Start: `docker run -d --name app -p 8080:8080 -e OPENROUTER_API_KEY=ci-placeholder-not-a-key -e MODEL_ROUTER=ci/placeholder -e MODEL_CLASSIFIER=ci/placeholder -e MODEL_ANSWER=ci/placeholder -e MODEL_EMBEDDINGS="$(jq -r .embedding_model data/index/manifest.json)" dw-companion:ci`. Langfuse keys are omitted, so spec 007's `NullTracer` is used.
4. `infra/smoke.sh http://127.0.0.1:8080`.
5. `if: failure()`: `docker logs app`.

## Validation Rules

| Subject | Input | Rule | Failure |
|---------|-------|------|---------|
| `ApiSettings` | `SITE_DIR` | Empty/whitespace → `None`. Otherwise the resolved path must be an existing directory containing a file `index.html`. | `ConfigError` entry `SITE_DIR must be a directory containing index.html`, listed together with any other `ApiSettings` problems (spec 008 style), raised by `create_app` |
| `deploy.sh`/`setup.sh` | `GCP_PROJECT` | Required; `^[a-z][a-z0-9-]{4,28}[a-z0-9]$` | `<script>: error: GCP_PROJECT must be a GCP project id`, exit 1 |
| `deploy.sh`/`setup.sh` | `GCP_REGION` | Empty → `europe-west1`; otherwise `^[a-z]+-[a-z]+[0-9]+$` | error, exit 1 |
| `deploy.sh` | `MIN_INSTANCES` | Empty → `1`; otherwise exactly `0` or `1` | error, exit 1 |
| `deploy.sh` | working tree | `git status --porcelain` empty | error, exit 1 |
| `deploy.sh` | index | `data/index/manifest.json` exists | error, exit 1 |
| `setup.sh` | secret value prompt | Non-empty | re-prompt is not offered; error, exit 1 (re-run the script) |
| `smoke.sh` | `BASE_URL` | Required; starts with `http://` or `https://` | `smoke: error: usage: infra/smoke.sh BASE_URL`, exit 2 |
| `infra/runtime-env.yaml` | every non-blank, non-comment line | `^[A-Z][A-Z0-9_]*: "[^"\\]*"$`; keys unique; each key is a key in `.env.example`; no key in {`OPENROUTER_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `SITE_DIR`}; `CHAT_TRUSTED_PROXY_HOPS` is `"1"`; `MODEL_EMBEDDINGS` equals the manifest's `embedding_model` | test failure (*Testing*) |
| `Dockerfile` | `ARG UV_VERSION` | `^\d+\.\d+\.\d+$` | test failure |

## Authorization & Security

The service is public and anonymous by design (handoff 3); spec 008's guards are the only request-level controls.

| Action | Who | Enforcement |
|--------|-----|-------------|
| Read site, call `/api/*` | anyone | `--allow-unauthenticated` (`allUsers` invoker); spec 008 D8 guards on `/api/chat` |
| Read secrets at runtime | `dw-companion-run` service account only | `roles/secretmanager.secretAccessor` bound per secret (D8) |
| Build, push, deploy, run setup | the owner's local `gcloud` credentials | No CI or agent credentials exist (D5) |
| Billing budgets, OpenRouter limits, Langfuse | the owner, in the respective consoles | Not automated (D13) |

- **Secrets never enter the repo, the image or the build.** Allow-list `.dockerignore`; no `ARG`/`ENV` carries a key; `setup.sh` reads values hidden from the terminal and passes them on stdin; Cloud Run injects them as env vars at instance start. `ci.yml` uses only obviously fake placeholders and references no `secrets.`.
- **Cost bounds in production:** spec 008's daily cap and rate limit, made effective by `max-instances=1`/`min-instances=1` (D1); request timeout 120 s; `max_tokens` on every call (spec 006/007); OpenRouter key limit and GCP budget alert (owner, D13). Residual risk: open risk (c).
- **Privacy:** uvicorn access log off (client IPs are never logged, spec 008 D17). Cloud Run's own request logs record client IPs in Cloud Logging, which is platform behaviour outside the app; `docs/deploy.md` states this, and nothing is forwarded to Langfuse.
- **Container hardening:** non-root user, read-only root-owned app files, no shell tools added, no `vendor/`, tests or dev dependencies in the image.
- **Transport:** Cloud Run terminates TLS; the slash redirect stays on `https` (D4).

## Testing

pytest, plain functions, flat files in `backend/tests/` (spec 005 D15), `REPO_ROOT = Path(__file__).resolve().parents[2]` as in spec 001. All offline. HTTP tests reuse spec 008's `api_helpers.make_client` and fakes; site fixtures are written to `tmp_path` by a local helper `make_site(tmp_path) -> Path` that creates `site/index.html` (`<p>home</p>`), `site/rules/x/index.html` (`<p>rule x</p>`), `site/404.html` (`<p>missing</p>`) and, outside the site directory, `tmp_path/secret.txt` (`top secret`).

**`test_api_settings.py`** (additive)
- `test_site_dir_unset_is_none`: `{}` and `{"SITE_DIR": "  "}` give `site_dir is None`.
- `test_site_dir_parsed_and_resolved`: a `make_site` directory gives that absolute path.
- `test_site_dir_must_contain_index`: a missing directory and an empty existing directory each raise `ConfigError` containing `SITE_DIR must be a directory containing index.html`; combined with `CHAT_RATE_PER_MINUTE="0"`, one `ConfigError` names both variables.

**`test_api_site.py`** (new; every case except `test_chat_still_streams_with_site_mounted` also asserts `FakeLLMClient.requests == []`)
- `test_site_not_mounted_by_default`: without `SITE_DIR`, `GET /` gives 404 and the body does not contain `home`.
- `test_home_served`: `GET /` gives 200, `text/html`, body contains `<p>home</p>`.
- `test_directory_index_served`: `GET /rules/x/` gives `<p>rule x</p>`.
- `test_slashless_directory_redirects`: `GET /rules/x` with `follow_redirects=False` gives 307 and a `Location` ending in `/rules/x/`.
- `test_unknown_path_serves_404_page`: `GET /nope/` and `GET /api/nope` give 404 with `<p>missing</p>`.
- `test_api_routes_take_precedence`: with the site mounted, `GET /api/health` gives 200 `{"status": "ok"}` with `Cache-Control: no-store`, and `POST /api/chat` with `{}` gives 422 `invalid_request` JSON.
- `test_chat_still_streams_with_site_mounted`: spec 008's out_of_scope turn gives `status` router, `status` out_of_scope, `reply` (router request count 1).
- `test_path_traversal_blocked`: `GET /../secret.txt` and `GET /%2e%2e/secret.txt` never return 200 and never contain `top secret`.
- `test_post_to_static_path_not_allowed`: `POST /` gives 405.

**`test_deploy_config.py`** (new; static checks on committed files; helpers split the `Dockerfile` into stages at `FROM` lines)
- `test_dockerignore_is_allow_list`: the first non-comment line is `*`; the set of `!` lines is exactly {`!pyproject.toml`, `!uv.lock`, `!.python-version`, `!backend/`, `!data/normalized/`, `!data/index/`, `!site/`}; `backend/tests/` and `site/node_modules/` are excluded lines.
- `test_dockerfile_never_copies_secrets_or_vendor`: no `COPY`/`ADD` line mentions `vendor`, `.env` or `.git`, and no `ARG`/`ENV` line names `OPENROUTER_API_KEY` or `LANGFUSE_`.
- `test_runtime_stage_runs_as_non_root`: the last stage contains `USER app` after its final `COPY`.
- `test_runtime_command_matches_api_constraints`: the `CMD` line contains `backend.api.app:create_app`, `--factory`, `--workers 1`, `--no-access-log`, `--proxy-headers` and `${PORT:-8080}`.
- `test_runtime_stage_sets_site_dir`: the last stage's `ENV` sets `SITE_DIR=/app/site/dist` and copies `--from=site /src/site/dist/`.
- `test_image_versions_match_toolchain`: `PYTHON_IMAGE`'s tag starts with the content of `.python-version` followed by `-`; `NODE_IMAGE`'s tag major equals `site/.nvmrc`; `UV_VERSION` matches `^\d+\.\d+\.\d+$`.
- `test_infra_scripts_are_strict_and_executable`: `setup.sh`, `deploy.sh`, `smoke.sh` start with `#!/usr/bin/env bash`, contain `set -euo pipefail`, and `os.access(path, os.X_OK)`.
- `test_deploy_pins_single_instance_and_secrets`: `deploy.sh` contains `--max-instances=1`, `--min-instances="$MIN_INSTANCES"`, `--allow-unauthenticated`, `--env-vars-file=infra/runtime-env.yaml`, the three `NAME=<secret-id>:latest` pairs from D7, and the `MIN_INSTANCES` default `1`.
- `test_runtime_env_file_is_valid`: every rule in the `infra/runtime-env.yaml` row of *Validation Rules*. The `MODEL_EMBEDDINGS` comparison is skipped with reason `data/index/manifest.json not committed (spec 007 open risk f)` when the manifest is absent; every other assertion still runs.
- `test_secret_env_vars_documented`: `OPENROUTER_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` are keys in `.env.example`.
- `test_cleanup_policy_keeps_recent_versions`: the JSON parses, and has one `Keep` policy with `keepCount` 3 and one `Delete` policy.

**CI:** the `image` job (*CI Image Job*) is the image-level test. **Manual:** `bash -n infra/*.sh` exits 0; `make image` succeeds locally; `docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local` then `make smoke URL=http://127.0.0.1:8080` passes. The explicit `-e SITE_DIR=…` is required: `.env` contains `SITE_DIR=` (empty, from `.env.example`), and an `--env-file` entry overrides the image's `ENV` default, which would disable the site; `-e` takes precedence over `--env-file`. Live checks are in *Owner Gate*.

## Documentation

- **`docs/deploy.md`** (new), sections in this order:
  1. `## Overview`: the architecture diagram from this spec and the D1 limitation in two sentences.
  2. `## Owner account setup (manual, before the first deploy)`: GCP project with billing (a personal project, not under an org with domain-restricted sharing); **GCP budget alert** on the project (Billing → Budgets & alerts, monthly amount chosen by the owner, e.g. 10 USD, email alerts at 50%, 90%, 100% of actual and 100% of forecast; alerts notify, they do not stop spend); **OpenRouter**: a dedicated production API key with a credit limit, auto top-up off, so the prepaid balance bounds the loss; **Langfuse**: a cloud free-tier project and its key pair (note the free tier's monthly observation allowance). States plainly that no script performs these steps.
  3. `## One-time GCP setup`: `gcloud auth login`, `make gcp-setup GCP_PROJECT=<id>`, what it creates (D7, D8, D15) and that it prompts for the three secret values.
  4. `## Deploy`: `make deploy GCP_PROJECT=<id>` (clean tree required; `MIN_INSTANCES=0` override and its consequence, D1); the smoke check; Apple Silicon note (open risk g).
  5. `## Verify guardrails live`: the Owner Gate step 6 procedure.
  6. `## Operations`: rollback (`gcloud run revisions list --service dw-companion --region <r>` then `gcloud run services update-traffic dw-companion --region <r> --to-revisions <revision>=100`); secret rotation (`gcloud secrets versions add <id> --data-file=-`, then `make deploy`); changing models or limits (edit `infra/runtime-env.yaml`, commit, deploy; embeddings change also needs an index rebuild); counters reset on each deploy (open risk c); memory and CPU-throttling notes (open risks a, e); Cloud Run request logs contain client IPs (platform, not app).
  7. `Live URL:` line, filled in by the owner after the first deploy (D14).
- **ADR "Deploy: one Cloud Run service with min and max instances 1"** (D1–D5, D8–D11, D13): must state both handoff discrepancies (D1, D2) with reasoning, the owner review item on idle cost, and that budget guards are owner actions.
- **`README.md`**: under `## Development`, add `### Running the container and deploying`: `make image`; `docker run --env-file .env -e SITE_DIR=/app/site/dist -p 8080:8080 dw-companion:local` then open `http://localhost:8080/` (with a one-line note that the `-e SITE_DIR` is needed because the empty `SITE_DIR=` in `.env` would otherwise override the image default and serve only the API); to serve the site without Docker, `npm run build` in `site/` then start the API as in spec 008 with `SITE_DIR=site/dist`; deployment is in [`docs/deploy.md`](docs/deploy.md).

## Suggested Story Breakdown

1. **[backend] Serve the static site from the API.** `SITE_DIR` in `settings.py`, the mount in `app.py`, `.env.example`, `test_api_settings.py` additions, `test_api_site.py`. Verifiable with pytest, and locally with `npm run build` + uvicorn `SITE_DIR=site/dist` on one port. Depends on spec 008.
2. **[infra] Container image and CI smoke.** `Dockerfile`, `.dockerignore`, `infra/smoke.sh`, `Makefile` `image`/`smoke`, the CI `image` job, `test_deploy_config.py` Dockerfile/`.dockerignore`/version/script-mode cases. Verifiable: `make image`, container + `make smoke`, CI green. Depends on 1, spec 009 (`Makefile`), spec 007's committed index (open risk f).
3. **[infra] GCP setup and deploy scripts, runbook.** `infra/setup.sh`, `infra/deploy.sh`, `infra/runtime-env.yaml`, `infra/ar-cleanup-policy.json`, `Makefile` `gcp-setup`/`deploy`, remaining `test_deploy_config.py` cases, delete `infra/.gitkeep`, `docs/deploy.md`, the ADR (number per D17: highest `## ADR-NNN` in `docs/decisions.md` + 1), the README subsection. Verifiable offline: tests and `bash -n`; no GCP access needed. Depends on 2.
4. **Owner gate (not a feature-builder story; story-creator emits it as an owner checklist, not an implementation task).** See *Owner Gate*. Depends on 3.

## Owner Gate

Performed by the owner with their own accounts; no agent can do these steps.
1. Review D1 (idle cost of `min-instances=1`) and decide `MIN_INSTANCES`.
2. Account setup from `docs/deploy.md` section 2: GCP project and **budget alert**, OpenRouter production key with **credit limit** and auto top-up off, Langfuse project.
3. `make gcp-setup GCP_PROJECT=<id>`, entering the three secret values.
4. `make deploy GCP_PROJECT=<id>`; the smoke check passes against the `https://` URL.
5. In a browser: the home page and a rules page load; on `/assistant/`, "How does Hack and Slash work?" shows progress, then an answer with citation links that open `/rules/…/` pages on the same host.
6. Guardrails live (each request is a cheap out-of-scope turn, message `hello`):
   - **Rate limit and spoofing:** send 6 valid requests within a minute, each with a different `X-Forwarded-For: 198.51.100.<n>` header; requests 1–5 get 200, request 6 gets 429 `rate_limited`. (If 6 succeeds, hops are wrong: the key varies per request.)
   - **Per visitor:** while still limited, one request from a different network (e.g. phone on mobile data) gets 200. (If it gets 429, the key is a proxy address.)
   - **Spend cap:** `gcloud run services update dw-companion --region <r> --update-env-vars CHAT_DAILY_BUDGET_USD=0.0001`; the first request gets 200, the second gets 503 `budget_exhausted`; then `make deploy` restores the committed config.
   - On any failure, adjust `CHAT_TRUSTED_PROXY_HOPS` in `infra/runtime-env.yaml` (open risk b), redeploy and repeat.
7. Langfuse shows the step 5 and 6 turns with model, tokens and cost under the production session ids (open risk a).
8. Record the URL on the `Live URL:` line of `docs/deploy.md` and commit.

## Success Criteria

Automated:
- [ ] Every test in *Testing* exists and passes with `uv run pytest`; every spec 008 test passes unmodified.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` exit 0.
- [ ] The CI `image` job builds the image and `infra/smoke.sh` reports all 7 checks passed; `ci.yml` contains no `secrets.`.
- [ ] `bash -n infra/setup.sh infra/deploy.sh infra/smoke.sh` exits 0.
- [ ] No new Python or npm dependency is added.
- [ ] `docs/deploy.md`, the ADR and the README subsection exist; `.env.example` has `SITE_DIR`.

Owner verification (milestone 10 acceptance):
- [ ] The service runs with `max-instances=1` and the chosen `min-instances` (`gcloud run services describe` shows them).
- [ ] The three keys are Secret Manager references in the service config, not plain env values.
- [ ] Every *Owner Gate* step 6 check passed on the live URL.
- [ ] A GCP budget alert exists on the project and the production OpenRouter key has a credit limit.
- [ ] `docs/deploy.md` contains the live `https://` URL.

## Future Considerations

- Persistent spend/rate state (Firestore) so `min-instances=0` becomes safe (spec 008 D9).
- Custom domain and, then, Astro `site` for canonical URLs and a sitemap (spec 004 Future Considerations).
- Long-lived `Cache-Control` for Astro's hashed `/_astro/` assets, gzip, and security headers (CSP).
- Deploy from GitHub Actions via Workload Identity Federation on pushes to `main`.
- Pin base images by digest with automated updates.
