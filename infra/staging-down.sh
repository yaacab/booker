#!/usr/bin/env bash
# Tear down isolated staging compose project. Does not touch production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not available; nothing to stop" >&2
  exit 0
fi
docker compose -f "${ROOT}/infra/docker-compose.yml" -f "${ROOT}/infra/docker-compose.staging.yml" --profile staging down
echo "staging compose down project=${COMPOSE_PROJECT_NAME}"
