#!/usr/bin/env bash
set -euo pipefail

if [[ ${GITHUB_REPOSITORY:-} != kamyar/emoji-maker || ${GITHUB_REF:-} != refs/heads/main ]]; then
    echo "Production deployment requires kamyar/emoji-maker on main." >&2
    exit 1
fi

if [[ -z ${GH_TOKEN:-} ]]; then
    echo "::error::Set the KAMYME_DEPLOY_TOKEN Actions secret with Contents write access to kamyar/kamyme."
    exit 1
fi

image=$(docker image inspect "ghcr.io/kamyar/emoji-maker:${GITHUB_SHA:?}" \
    --format '{{index .RepoDigests 0}}')
if [[ ! $image =~ ^ghcr\.io/kamyar/emoji-maker@sha256:[0-9a-f]{64}$ ]]; then
    echo "::error::The published application image must have an immutable GHCR digest."
    exit 1
fi

gh api --hostname github.com --method POST repos/kamyar/kamyme/dispatches \
    --header 'Accept: application/vnd.github+json' \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    --raw-field 'event_type=emoji-maker-image' \
    --raw-field 'client_payload[service]=emoji-maker' \
    --raw-field "client_payload[image]=${image}"

printf 'Production deployment requested for %s.\n' "$image"
