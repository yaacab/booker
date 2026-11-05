#!/usr/bin/env bash
# Stop staging harness apps + compose project. Does not delete foreign volumes.
# Only kills PIDs we own (cmdline ownership check). Never kills foreign processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="/tmp/booker-staging"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"

stop_owned_pid() {
  local name="$1"
  local pidfile="${PID_DIR}/${name}.pid"
  if [[ ! -f "${pidfile}" ]]; then
    return 0
  fi
  local pid
  pid="$(tr -d '[:space:]' <"${pidfile}" || true)"
  rm -f "${pidfile}"
  rm -f "${PID_DIR}/${name}.sha"
  if [[ -z "${pid}" ]] || ! [[ "${pid}" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  if python3 -c "import sys; sys.path.insert(0,'${ROOT}/infra'); from staging_preflight import pid_owned_by_booker_staging; sys.exit(0 if pid_owned_by_booker_staging(int('${pid}')) else 1)"; then
    echo "staging-down: stopping owned ${name} pid ${pid}"
    kill "${pid}" || true
    sleep 1
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" || true
    fi
  else
    echo "staging-down: refuse to kill foreign pid ${pid} (stale ${name}.pid)" >&2
  fi
}

stop_owned_pid api
stop_owned_pid web

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
  echo "docker not available; owned app pidfiles cleared if present"
fi
