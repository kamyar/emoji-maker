#!/usr/bin/env bash
set -euo pipefail

PROJECT="emoji-maker-devbox"
REGION="europe-west1"

echo ">> Submitting build with kaniko caching..."
gcloud builds submit \
  --config cloudbuild.yaml \
  --project "$PROJECT" \
  --region "$REGION" \
  .

echo ">> Deploy complete!"
echo ">> https://emoji-maker-245051511324.${REGION}.run.app"
