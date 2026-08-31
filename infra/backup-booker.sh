#!/usr/bin/env bash
# Daily backup: SQLite (pilot) or Postgres when BOOKER_DATABASE_URL is set.
set -euo pipefail

BACKUP_ROOT="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
RETENTION_DAYS="${BOOKER_BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_ROOT}"

DB_URL="${BOOKER_DATABASE_URL:-sqlite:////opt/booker/data/booker.db}"

if [[ "${DB_URL}" == sqlite:* ]]; then
  SQLITE_PATH="${DB_URL#sqlite://}"
  OUT="${BACKUP_ROOT}/booker-${STAMP}.db.gz"
  sqlite3 "${SQLITE_PATH}" ".backup '${BACKUP_ROOT}/booker-${STAMP}.db'"
  gzip -f "${BACKUP_ROOT}/booker-${STAMP}.db"
  echo "sqlite backup: ${OUT}"
elif [[ "${DB_URL}" == postgres* ]]; then
  OUT="${BACKUP_ROOT}/booker-pg-${STAMP}.dump.gz"
  pg_dump "${DB_URL}" | gzip -c > "${OUT}"
  echo "postgres backup: ${OUT}"
else
  echo "unsupported BOOKER_DATABASE_URL: ${DB_URL}" >&2
  exit 1
fi

find "${BACKUP_ROOT}" -type f \( -name 'booker-*.gz' -o -name 'booker-pg-*.gz' \) -mtime +"${RETENTION_DAYS}" -delete
