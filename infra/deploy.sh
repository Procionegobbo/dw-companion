#!/usr/bin/env bash
# Build, push and deploy the dw-companion Cloud Run service (spec 011).
# Requires infra/setup.sh to have run at least once against the same GCP_PROJECT.
set -euo pipefail
cd "$(dirname "$0")/.."

GCP_PROJECT="${GCP_PROJECT:-}"
if [[ ! "$GCP_PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "deploy: error: GCP_PROJECT must be a GCP project id" >&2
  exit 1
fi

if [[ -z "${GCP_REGION:-}" ]]; then
  GCP_REGION="europe-west1"
elif [[ ! "$GCP_REGION" =~ ^[a-z]+-[a-z]+[0-9]+$ ]]; then
  echo "deploy: error: GCP_REGION must look like a GCP region (e.g. europe-west1)" >&2
  exit 1
fi

if [[ -z "${MIN_INSTANCES:-}" ]]; then
  MIN_INSTANCES="1"
elif [[ "$MIN_INSTANCES" != "0" && "$MIN_INSTANCES" != "1" ]]; then
  echo "deploy: error: MIN_INSTANCES must be 0 or 1" >&2
  exit 1
fi

for cmd in gcloud docker git curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "deploy: error: $cmd must be on PATH" >&2
    exit 1
  fi
done

if [[ -n "$(git status --porcelain)" ]]; then
  echo "deploy: error: working tree is not clean; commit or stash first" >&2
  exit 1
fi

if [[ ! -f data/index/manifest.json ]]; then
  echo "deploy: error: data/index/manifest.json is missing; build the retrieval index first" >&2
  exit 1
fi

if [[ "$MIN_INSTANCES" == "0" ]]; then
  echo "deploy: warning: MIN_INSTANCES=0 lets the daily spend cap reset on every cold start (see docs/deploy.md)"
fi

tag="$(git rev-parse --short=12 HEAD)"
image="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/dw-companion/app:$tag"
sa_email="dw-companion-run@$GCP_PROJECT.iam.gserviceaccount.com"

docker buildx build --platform linux/amd64 -t "$image" --push .

gcloud run deploy dw-companion --project "$GCP_PROJECT" --region "$GCP_REGION" --image "$image" \
  --service-account "$sa_email" \
  --allow-unauthenticated --port=8080 --cpu=1 --memory=512Mi --concurrency=80 --timeout=120 \
  --cpu-throttling --min-instances="$MIN_INSTANCES" --max-instances=1 \
  --env-vars-file=infra/runtime-env.yaml \
  --set-secrets=OPENROUTER_API_KEY=dw-companion-openrouter-api-key:latest,LANGFUSE_PUBLIC_KEY=dw-companion-langfuse-public-key:latest,LANGFUSE_SECRET_KEY=dw-companion-langfuse-secret-key:latest \
  --quiet

url="$(gcloud run services describe dw-companion --project "$GCP_PROJECT" \
  --region "$GCP_REGION" --format='value(status.url)')"
echo "deploy: live at $url (image $tag)"

if ! infra/smoke.sh "$url"; then
  echo "deploy: error: smoke check failed." >&2
  echo "deploy: to roll back, see 'Operations' in docs/deploy.md:" >&2
  echo "deploy:   gcloud run revisions list --service dw-companion --region $GCP_REGION" >&2
  echo "deploy:   gcloud run services update-traffic dw-companion --region $GCP_REGION --to-revisions <revision>=100" >&2
  exit 1
fi
