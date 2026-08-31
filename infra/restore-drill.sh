#!/usr/bin/env bash
# Restore drill for SQLite pilot backups. Run on staging or isolated path only.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <backup.db.gz> [restore_dir]" >&2
  exit 1
fi

BACKUP="$1"
RESTORE_DIR="${2:-/tmp/booker-restore-drill}"
DB_PATH="${RESTORE_DIR}/booker.db"

mkdir -p "${RESTORE_DIR}"
gunzip -c "${BACKUP}" > "${DB_PATH}"

if ! sqlite3 "${DB_PATH}" "SELECT 1 FROM users LIMIT 1;" >/dev/null 2>&1; then
  echo "restore drill FAILED: users table unreadable" >&2
  exit 1
fi

echo "restore drill OK: ${DB_PATH}"
echo "RTO note: record manual time from backup selection to this message in MASTER_PLAN journal"
