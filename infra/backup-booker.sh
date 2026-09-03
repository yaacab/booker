#!/usr/bin/env bash
# Daily backup: SQLite (pilot) or Postgres when BOOKER_DATABASE_URL is set.
# Archives BOOKER_UPLOAD_DIR atomically with the database.
set -euo pipefail

BACKUP_ROOT="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/opt/booker/data/uploads}"
RETENTION_DAYS="${BOOKER_BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_ROOT}"

DB_URL="${BOOKER_DATABASE_URL:-sqlite:////opt/booker/data/booker.db}"

pg_url_for_libpq() {
  local url="$1"
  url="${url/postgresql+psycopg/postgresql}"
  url="${url/postgres+psycopg/postgresql}"
  echo "${url}"
}

stage_uploads() {
  local staging="$1"
  if [[ -d "${UPLOAD_DIR}" ]]; then
    cp -a "${UPLOAD_DIR}" "${staging}/uploads"
  else
    mkdir -p "${staging}/uploads"
  fi
}

if [[ "${DB_URL}" == sqlite:* ]]; then
  SQLITE_PATH="${DB_URL#sqlite://}"
  STAGING="${BACKUP_ROOT}/.staging-${STAMP}"
  mkdir -p "${STAGING}"
  sqlite3 "${SQLITE_PATH}" ".backup '${STAGING}/booker.db'"
  stage_uploads "${STAGING}"
  OUT="${BACKUP_ROOT}/booker-${STAMP}.tar.gz"
  tar -czf "${OUT}" -C "${STAGING}" booker.db uploads
  rm -rf "${STAGING}"
  echo "sqlite backup: ${OUT} (db + uploads)"
elif [[ "${DB_URL}" == postgres* ]]; then
  STAGING="${BACKUP_ROOT}/.staging-${STAMP}"
  mkdir -p "${STAGING}"
  pg_dump "$(pg_url_for_libpq "${DB_URL}")" > "${STAGING}/booker.dump"
  stage_uploads "${STAGING}"
  OUT="${BACKUP_ROOT}/booker-pg-${STAMP}.tar.gz"
  tar -czf "${OUT}" -C "${STAGING}" booker.dump uploads
  rm -rf "${STAGING}"
  echo "postgres backup: ${OUT} (dump + uploads)"
else
  echo "unsupported BOOKER_DATABASE_URL: ${DB_URL}" >&2
  exit 1
fi

find "${BACKUP_ROOT}" -type f \( -name 'booker-*.tar.gz' -o -name 'booker-pg-*.tar.gz' \) -mtime +"${RETENTION_DAYS}" -delete
