#!/usr/bin/env bash
# One-time, idempotent GCP setup for the dw-companion Cloud Run service (spec 011).
# Creates the APIs, Artifact Registry repository, runtime service account and the
# three Secret Manager secrets the service reads at runtime. Safe to re-run: every
# step is skipped when it is already done. Never echoes a secret value.
set -euo pipefail
cd "$(dirname "$0")/.."

GCP_PROJECT="${GCP_PROJECT:-}"
if [[ ! "$GCP_PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "setup: error: GCP_PROJECT must be a GCP project id" >&2
  exit 1
fi

if [[ -z "${GCP_REGION:-}" ]]; then
  GCP_REGION="europe-west1"
elif [[ ! "$GCP_REGION" =~ ^[a-z]+-[a-z]+[0-9]+$ ]]; then
  echo "setup: error: GCP_REGION must look like a GCP region (e.g. europe-west1)" >&2
  exit 1
fi

sa_email="dw-companion-run@$GCP_PROJECT.iam.gserviceaccount.com"

# 1. Required APIs. gcloud services enable is itself idempotent.
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com --project "$GCP_PROJECT"

# 2. Artifact Registry Docker repository, plus the cleanup policy (always applied).
if ! gcloud artifacts repositories describe dw-companion \
  --project "$GCP_PROJECT" --location "$GCP_REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create dw-companion \
    --project "$GCP_PROJECT" --location "$GCP_REGION" --repository-format=docker
fi
gcloud artifacts repositories set-cleanup-policies dw-companion \
  --project "$GCP_PROJECT" --location "$GCP_REGION" \
  --policy=infra/ar-cleanup-policy.json --no-dry-run

# 3. Runtime service account.
if ! gcloud iam service-accounts describe "$sa_email" --project "$GCP_PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create dw-companion-run \
    --project "$GCP_PROJECT" --display-name "dw-companion Cloud Run runtime"
fi

# 4. Secrets: create if missing, prompt for a value if no version is enabled yet,
#    then (re-)bind read access to the runtime service account.
for secret_id in \
  dw-companion-openrouter-api-key \
  dw-companion-langfuse-public-key \
  dw-companion-langfuse-secret-key
do
  if ! gcloud secrets describe "$secret_id" --project "$GCP_PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$secret_id" --project "$GCP_PROJECT" --replication-policy=automatic
  fi

  enabled_version="$(gcloud secrets versions list "$secret_id" --project "$GCP_PROJECT" \
    --filter=state:enabled --limit=1 --format='value(name)')"
  if [[ -z "$enabled_version" ]]; then
    printf 'Value for %s (input hidden): ' "$secret_id" >&2
    read -rs value
    printf '\n' >&2
    if [[ -z "$value" ]]; then
      echo "setup: error: no value entered for $secret_id" >&2
      exit 1
    fi
    printf '%s' "$value" | gcloud secrets versions add "$secret_id" \
      --project "$GCP_PROJECT" --data-file=-
  fi

  gcloud secrets add-iam-policy-binding "$secret_id" --project "$GCP_PROJECT" \
    --member "serviceAccount:$sa_email" --role roles/secretmanager.secretAccessor
done

# 5. Docker credential helper for the Artifact Registry region.
gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev" --quiet

echo "setup: done"
echo "setup: next: make deploy GCP_PROJECT=$GCP_PROJECT"
