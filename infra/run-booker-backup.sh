#!/usr/bin/env bash
# Load the same protected runtime environment as booker-api, then run a backup.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BOOKER_ENV_FILE:-/etc/booker/booker-api.env}"
PY="${BOOKER_PYTHON:-}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  else
    PY="python3"
  fi
fi
if [[ -z "${BOOKER_DATABASE_URL:-}" ]]; then
  BOOKER_DATABASE_URL="$(${PY} "${ROOT}/infra/backup_support.py" env-value "${ENV_FILE}" BOOKER_DATABASE_URL)"
fi
export BOOKER_DATABASE_URL BOOKER_PYTHON="${PY}"

if [[ "${BOOKER_BACKUP_FORMAT:-legacy}" == "sealed" ]]; then
  if [[ -z "${BOOKER_BACKUP_KEY_FILE:-}" ]]; then
    echo "BOOKER_BACKUP_KEY_FILE is required for sealed backups" >&2
    exit 1
  fi
  "${BOOKER_BACKUP_CRYPTO_PYTHON:-${PY}}" "${ROOT}/infra/backup_crypto.py" \
    check-key "${BOOKER_BACKUP_KEY_FILE}"
fi

SERVICE="${BOOKER_BACKUP_QUIESCE_SERVICE:-}"
WAS_ACTIVE=0
if [[ -n "${SERVICE}" ]] && command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "${SERVICE}"; then
  WAS_ACTIVE=1
fi
cleanup() {
  if [[ "${WAS_ACTIVE}" == "1" ]]; then
    systemctl start "${SERVICE}"
  fi
}
trap cleanup EXIT
if [[ "${WAS_ACTIVE}" == "1" ]]; then
  systemctl stop "${SERVICE}"
fi
"${ROOT}/infra/backup-booker.sh"
