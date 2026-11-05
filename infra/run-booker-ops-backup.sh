#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
EVIDENCE="${BOOKER_OPS_BACKUP_EVIDENCE_FILE:-${BACKUP_DIR}/.ops-backup.json}"
install -d -m 700 "${BACKUP_DIR}"
result=0
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${ROOT}/infra/run-booker-backup.sh" "$@" || result=$?
if [[ "${result}" != "0" ]]; then
  python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" backup "${started_at}" || result=1
fi
exit "${result}"
