#!/usr/bin/env bash
# Restore drill for booker backups (SQLite tar.gz with db + uploads). Staging only.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <backup.tar.gz> [restore_dir]" >&2
  exit 1
fi

BACKUP="$1"
RESTORE_DIR="${2:-/tmp/booker-restore-drill}"
DB_PATH="${RESTORE_DIR}/booker.db"
UPLOAD_PATH="${RESTORE_DIR}/uploads"

mkdir -p "${RESTORE_DIR}"
tar -xzf "${BACKUP}" -C "${RESTORE_DIR}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "restore drill FAILED: booker.db missing in archive" >&2
  exit 1
fi

if ! sqlite3 "${DB_PATH}" "SELECT 1 FROM users LIMIT 1;" >/dev/null 2>&1; then
  echo "restore drill FAILED: users table unreadable" >&2
  exit 1
fi

if [[ ! -d "${UPLOAD_PATH}" ]]; then
  echo "restore drill FAILED: uploads directory missing in archive" >&2
  exit 1
fi

echo "restore drill OK: ${DB_PATH} + ${UPLOAD_PATH}"
echo "RTO note: record manual time from backup selection to this message in MASTER_PLAN journal"
