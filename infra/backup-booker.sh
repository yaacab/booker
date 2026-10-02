#!/usr/bin/env bash
# Daily backup: SQLite (pilot) or Postgres when BOOKER_DATABASE_URL is set.
# Archives an online DB snapshot with a verified copy of BOOKER_UPLOAD_DIR.
set -euo pipefail
umask 077

BACKUP_ROOT="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/opt/booker/data/uploads}"
RETENTION_DAYS="${BOOKER_BACKUP_RETENTION_DAYS:-30}"
RETENTION_DRY_RUN="${BOOKER_BACKUP_RETENTION_DRY_RUN:-0}"
BACKUP_FORMAT="${BOOKER_BACKUP_FORMAT:-legacy}"
if [[ ! "${RETENTION_DAYS}" =~ ^[0-9]+$ ]] || (( RETENTION_DAYS < 1 || RETENTION_DAYS > 3650 )); then
  echo "BOOKER_BACKUP_RETENTION_DAYS must be an integer from 1 to 3650" >&2
  exit 1
fi
if [[ "${RETENTION_DRY_RUN}" != "0" && "${RETENTION_DRY_RUN}" != "1" ]]; then
  echo "BOOKER_BACKUP_RETENTION_DRY_RUN must be 0 or 1" >&2
  exit 1
fi
if [[ "${BACKUP_FORMAT}" != "legacy" && "${BACKUP_FORMAT}" != "sealed" ]]; then
  echo "BOOKER_BACKUP_FORMAT must be legacy or sealed" >&2
  exit 1
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_ROOT}"
chmod 700 "${BACKUP_ROOT}"
exec 9>"${BACKUP_ROOT}/.backup.lock"
if ! flock -n 9; then
  echo "backup already running" >&2
  exit 1
fi

DB_URL="${BOOKER_DATABASE_URL:-sqlite:////opt/booker/data/booker.db}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${BOOKER_PYTHON:-}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  else
    PY="python3"
  fi
fi
SUPPORT="${ROOT}/infra/backup_support.py"
CRYPTO="${ROOT}/infra/backup_crypto.py"
CONTRACT="${ROOT}/infra/backup_contract.py"
EVIDENCE="${BOOKER_OPS_BACKUP_EVIDENCE_FILE:-${BACKUP_ROOT}/.ops-backup.json}"
CRYPTO_PY="${BOOKER_BACKUP_CRYPTO_PYTHON:-${PY}}"
KEY_FILE="${BOOKER_BACKUP_KEY_FILE:-}"
if [[ "${BACKUP_FORMAT}" == "sealed" ]]; then
  if [[ -z "${KEY_FILE}" ]]; then
    echo "BOOKER_BACKUP_KEY_FILE is required for sealed backups" >&2
    exit 1
  fi
  BOOKER_BACKUP_DIR="${BACKUP_ROOT}" BOOKER_UPLOAD_DIR="${UPLOAD_DIR}" \
    "${CRYPTO_PY}" "${CRYPTO}" check-key "${KEY_FILE}"
fi
if [[ "${BACKUP_FORMAT}" == "sealed" ]]; then
  # Plaintext staging must never be inside the archive directory copied off-site.
  STAGING_PARENT="${BOOKER_BACKUP_STAGING_PARENT:-/tmp}"
  STAGING_PARENT="$(cd "${STAGING_PARENT}" && pwd -P)"
  BACKUP_CANON="$(cd "${BACKUP_ROOT}" && pwd -P)"
  if [[ "${STAGING_PARENT}" == "${BACKUP_CANON}" || "${STAGING_PARENT}" == "${BACKUP_CANON}/"* ]]; then
    echo "sealed staging parent must be outside BOOKER_BACKUP_DIR" >&2
    exit 1
  fi
  find "${STAGING_PARENT}" -maxdepth 1 -mindepth 1 -type d -user "$(id -un)" \
    -name 'booker-sealed-staging-*' -mmin +1440 -exec rm -rf -- {} +
fi
STAGING=""
TEMP_OUT=""
cleanup() {
  if [[ -n "${TEMP_OUT}" ]]; then
    rm -f -- "${TEMP_OUT}"
  fi
  if [[ -n "${STAGING}" ]]; then
    rm -rf "${STAGING}"
  fi
}
trap cleanup EXIT

stage_uploads() {
  local staging="$1"
  "${PY}" "${SUPPORT}" snapshot-uploads "${UPLOAD_DIR}" "${staging}/uploads"
}

publish_archive() {
  local stem="$1"
  local db_name="$2"
  if [[ "${BACKUP_FORMAT}" == "sealed" ]]; then
    TEMP_OUT="$(mktemp "${BACKUP_ROOT}/${stem}-XXXXXX.bke.partial")"
    OUT="${TEMP_OUT%.partial}"
    tar -czf - -C "${STAGING}" "${db_name}" uploads backup-manifest.json | \
      BOOKER_BACKUP_DIR="${BACKUP_ROOT}" BOOKER_UPLOAD_DIR="${UPLOAD_DIR}" \
      "${CRYPTO_PY}" "${CRYPTO}" seal - "${KEY_FILE}" "${TEMP_OUT}"
    BOOKER_BACKUP_DIR="${BACKUP_ROOT}" BOOKER_UPLOAD_DIR="${UPLOAD_DIR}" \
      "${CRYPTO_PY}" "${CRYPTO}" verify "${TEMP_OUT}" "${KEY_FILE}"
  else
    TEMP_OUT="$(mktemp "${BACKUP_ROOT}/${stem}-XXXXXX.tar.gz.partial")"
    OUT="${TEMP_OUT%.partial}"
    tar -czf "${TEMP_OUT}" -C "${STAGING}" "${db_name}" uploads backup-manifest.json
    "${PY}" "${SUPPORT}" verify-archive "${TEMP_OUT}"
  fi
  chmod 600 "${TEMP_OUT}"
  "${PY}" "${CONTRACT}" publish "${TEMP_OUT}" "${OUT}"
  TEMP_OUT=""
  "${PY}" "${CONTRACT}" backup "${EVIDENCE}" "${OUT}" "${STAGING}/backup-manifest.json"
}

if [[ "${DB_URL}" == sqlite:* ]]; then
  SQLITE_PATH="${DB_URL#sqlite://}"
  if [[ "${BACKUP_FORMAT}" == "sealed" ]]; then
    STAGING="$(mktemp -d "${STAGING_PARENT}/booker-sealed-staging-${STAMP}-XXXXXX")"
  else
    STAGING="$(mktemp -d "${BACKUP_ROOT}/.staging-${STAMP}-XXXXXX")"
  fi
  "${PY}" "${SUPPORT}" sqlite-backup "${SQLITE_PATH}" "${STAGING}/booker.db"
  stage_uploads "${STAGING}"
  "${PY}" "${SUPPORT}" manifest "${STAGING}"
  publish_archive "booker-${STAMP}" booker.db
  rm -rf "${STAGING}"
  STAGING=""
  echo "sqlite backup: ${OUT} (db + uploads)"
elif [[ "${DB_URL}" == postgres* ]]; then
  if [[ "${BACKUP_FORMAT}" == "sealed" ]]; then
    STAGING="$(mktemp -d "${STAGING_PARENT}/booker-sealed-staging-${STAMP}-XXXXXX")"
  else
    STAGING="$(mktemp -d "${BACKUP_ROOT}/.staging-${STAMP}-XXXXXX")"
  fi
  SERVICE_FILE="${STAGING}/pg_service.conf"
  BOOKER_DATABASE_URL="${DB_URL}" "${PY}" "${SUPPORT}" pg-service "${SERVICE_FILE}"
  PGSERVICEFILE="${SERVICE_FILE}" pg_dump --format=custom --file="${STAGING}/booker.dump" "service=booker_backup"
  rm -f "${SERVICE_FILE}"
  stage_uploads "${STAGING}"
  "${PY}" "${SUPPORT}" manifest "${STAGING}"
  publish_archive "booker-pg-${STAMP}" booker.dump
  rm -rf "${STAGING}"
  STAGING=""
  echo "postgres backup: ${OUT} (dump + uploads)"
else
  echo "unsupported BOOKER_DATABASE_URL: ${DB_URL}" >&2
  exit 1
fi

if [[ "${RETENTION_DRY_RUN}" == "1" ]]; then
  find "${BACKUP_ROOT}" -maxdepth 1 -type f \( -name 'booker-*.tar.gz' -o -name 'booker-*.bke' \) \
    -mtime +"${RETENTION_DAYS}" -print
else
  find "${BACKUP_ROOT}" -maxdepth 1 -type f \( -name 'booker-*.tar.gz' -o -name 'booker-*.bke' \) \
    -mtime +"${RETENTION_DAYS}" -delete
fi
