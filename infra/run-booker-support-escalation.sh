#!/usr/bin/env bash
# Mutating local worker. Install a schedule only after reviewed schema, staff,
# backup/rollback and staging checks. It creates in-app notices, no external send.
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
exec "${PY}" -m booker_api.support_escalation "$@"
