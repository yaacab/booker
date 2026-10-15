#!/usr/bin/env bash
# Stop staging harness apps + compose project. Does not delete foreign volumes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="/tmp/booker-staging"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"

for name in api web; do
  if [[ -f "${PID_DIR}/${name}.pid" ]]; then
    pid="$(cat "${PID_DIR}/${name}.pid" || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" || true
    fi
    rm -f "${PID_DIR}/${name}.pid"
  fi
done

if command -v docker >/dev/null 2>&1; then
  ENV_FILE="${BOOKER_STAGING_ENV_FILE:-}"
  if [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
    docker compose -f "${ROOT}/infra/docker-compose.staging.yml" --env-file "${ENV_FILE}" down
  else
    docker compose -f "${ROOT}/infra/docker-compose.staging.yml" down || true
  fi
  # Never docker volume rm booker_pg or other non-staging volumes
  echo "staging compose down (volume booker_pg_staging retained; foreign volumes untouched)"
else
  echo "docker not available; app pidfiles cleared if present"
fi
