#!/usr/bin/env bash
# Local diagnostic checker; emits only aggregate counts and never sends alerts.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BOOKER_ENV_FILE:-/etc/booker/booker-api.env}"
PY="${BOOKER_PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then PY=python3; fi
if [[ -z "${BOOKER_DATABASE_URL:-}" ]]; then
  BOOKER_DATABASE_URL="$(${PY} "${ROOT}/infra/backup_support.py" env-value "${ENV_FILE}" BOOKER_DATABASE_URL)"
fi
export BOOKER_DATABASE_URL BOOKER_RUNTIME_ENV="${BOOKER_RUNTIME_ENV:-production}"
export PYTHONPATH="${ROOT}/apps/api${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PY}" -m booker_api.ops_monitor "$@"
