#!/usr/bin/env bash
set -euo pipefail

PROJECT="kamy-me"
REGION="europe-west1"
PROJECT_NUMBER="479242006620"

echo ">> Submitting build to ${PROJECT}..."
gcloud builds submit \
  --config cloudbuild.yaml \
  --project "$PROJECT" \
  --region "$REGION" \
  .

echo ">> Deploy complete!"
echo ">> https://emoji-maker-${PROJECT_NUMBER}.${REGION}.run.app"
