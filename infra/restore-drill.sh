#!/usr/bin/env bash
# Restore drill for booker backups (SQLite tar.gz with db + uploads). Staging only.
set -euo pipefail
umask 077

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <backup.tar.gz|backup.bke> [restore_dir]" >&2
  exit 1
fi

BACKUP="$1"
BACKUP_INPUT="${BACKUP}"
RESTORE_DIR="${2:-/tmp/booker-restore-drill}"
REQUIRE_SEALED="${BOOKER_BACKUP_REQUIRE_SEALED_RESTORE:-0}"
if [[ "${REQUIRE_SEALED}" != "0" && "${REQUIRE_SEALED}" != "1" ]]; then
  echo "BOOKER_BACKUP_REQUIRE_SEALED_RESTORE must be 0 or 1" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${BOOKER_PYTHON:-}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  else
    PY="python3"
  fi
fi
if ! RESTORE_DIR="$(${PY} "${ROOT}/infra/backup_support.py" validate-restore-target "${RESTORE_DIR}")"; then
  echo "restore drill FAILED: unsafe restore target" >&2
  exit 1
fi
DB_PATH="${RESTORE_DIR}/booker.db"
UPLOAD_PATH="${RESTORE_DIR}/uploads"
RESTORE_CREATED=0
SEALED_TMP=""
cleanup_failed_restore() {
  local result=$?
  if [[ -n "${SEALED_TMP}" ]]; then
    rm -rf -- "${SEALED_TMP}"
  fi
  if [[ "${result}" != "0" && "${RESTORE_CREATED}" == "1" ]]; then
    rm -rf -- "${RESTORE_DIR}"
  fi
}
trap cleanup_failed_restore EXIT
FORMAT="$(${PY} "${ROOT}/infra/backup_crypto.py" detect "${BACKUP}")"
if [[ "${BACKUP}" == *.bke && "${FORMAT}" != "sealed" ]]; then
  echo "sealed filename does not contain a sealed archive" >&2
  exit 1
fi
case "${FORMAT}" in
  sealed)
    KEY_FILE="${BOOKER_BACKUP_KEY_FILE:-}"
    if [[ -z "${KEY_FILE}" ]]; then
      echo "BOOKER_BACKUP_KEY_FILE is required for sealed restore" >&2
      exit 1
    fi
    CRYPTO_PY="${BOOKER_BACKUP_CRYPTO_PYTHON:-${PY}}"
    find /tmp -maxdepth 1 -mindepth 1 -type d -user "$(id -un)" \
      -name 'booker-sealed-restore-*' -mmin +1440 -exec rm -rf -- {} +
    SEALED_TMP="$(mktemp -d /tmp/booker-sealed-restore-XXXXXX)"
    BOOKER_BACKUP_DIR="${BOOKER_BACKUP_DIR:-}" BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-}" \
      "${CRYPTO_PY}" "${ROOT}/infra/backup_crypto.py" unseal \
      "${BACKUP}" "${KEY_FILE}" "${SEALED_TMP}/archive.tar.gz"
    BACKUP_INPUT="${SEALED_TMP}/archive.tar.gz"
    ;;
  legacy)
    if [[ "${REQUIRE_SEALED}" == "1" ]]; then
      echo "legacy tar.gz restore is disabled by BOOKER_BACKUP_REQUIRE_SEALED_RESTORE" >&2
      exit 1
    fi
    ;;
  *)
    echo "unsupported backup format" >&2
    exit 1
    ;;
esac
"${PY}" "${ROOT}/infra/backup_support.py" extract-verify "${BACKUP_INPUT}" "${RESTORE_DIR}"
RESTORE_CREATED=1

if [[ ! -f "${DB_PATH}" ]]; then
  echo "restore drill FAILED: booker.db missing in archive" >&2
  exit 1
fi

if ! "${PY}" "${ROOT}/infra/backup_support.py" sqlite-verify "${DB_PATH}"; then
  echo "restore drill FAILED: SQLite integrity, foreign keys or users table" >&2
  exit 1
fi

if [[ ! -d "${UPLOAD_PATH}" ]]; then
  echo "restore drill FAILED: uploads directory missing in archive" >&2
  exit 1
fi

echo "restore drill OK: ${DB_PATH} + ${UPLOAD_PATH}"
echo "RTO note: record manual time from backup selection to this message in MASTER_PLAN journal"
