#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
EVIDENCE="${BOOKER_OPS_RESTORE_EVIDENCE_FILE:-${BACKUP_DIR}/.ops-restore.json}"
BACKUP_EVIDENCE="${BOOKER_OPS_BACKUP_EVIDENCE_FILE:-${BACKUP_DIR}/.ops-backup.json}"
install -d -m 700 "${BACKUP_DIR}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ $# -lt 1 ]]; then
  python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
  exit 1
fi
if [[ -f "$1.evidence.json" || -L "$1.evidence.json" ]]; then
  BACKUP_EVIDENCE="$1.evidence.json"
fi
kind="$(python3 "${ROOT}/infra/backup_contract.py" classify "${BACKUP_EVIDENCE}")"
if [[ "${kind}" == "invalid" ]]; then
  python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
  exit 1
fi
if [[ "${kind}" == "v2" ]]; then
  if [[ -z "${BOOKER_DATABASE_URL:-}" ]]; then
    python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
    echo "BOOKER_DATABASE_URL is required for verified restore" >&2
    exit 1
  fi
  case "${BOOKER_DATABASE_URL}" in
    sqlite:*) engine=sqlite ;;
    postgres*) engine=postgresql ;;
    *)
      python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
      echo "unsupported BOOKER_DATABASE_URL engine" >&2
      exit 1
      ;;
  esac
  if ! python3 "${ROOT}/infra/backup_contract.py" verify "${BACKUP_EVIDENCE}" "$1" "${engine}"; then
    python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
    exit 1
  fi
  if [[ "${engine}" != "sqlite" ]]; then
    python3 "${ROOT}/infra/backup_contract.py" unknown "${EVIDENCE}" "${started_at}" postgresql_restore_unverified
    echo "PostgreSQL restore verifier is not configured" >&2
    exit 1
  fi
  COPY_DIR="$(mktemp -d /tmp/booker-ops-restore-XXXXXX)"
  trap 'rm -rf -- "${COPY_DIR}"' EXIT
  VERIFIED_COPY="${COPY_DIR}/$(basename -- "$1")"
  if ! cp --no-dereference -- "$1" "${VERIFIED_COPY}" ||
     ! python3 "${ROOT}/infra/backup_contract.py" verify "${BACKUP_EVIDENCE}" "${VERIFIED_COPY}" "${engine}"; then
    python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}"
    exit 1
  fi
  set -- "${VERIFIED_COPY}" "${2:-/tmp/booker-restore-drill}"
fi
result=0
"${ROOT}/infra/restore-drill.sh" "$@" || result=$?
if [[ "${result}" == "0" && "${kind}" == "v2" ]]; then
  python3 "${ROOT}/infra/backup_contract.py" restore "${EVIDENCE}" "${BACKUP_EVIDENCE}" "$1" "${2:-/tmp/booker-restore-drill}" "${started_at}" || result=1
fi
if [[ "${result}" != "0" ]]; then
  python3 "${ROOT}/infra/backup_contract.py" failure "${EVIDENCE}" restore "${started_at}" || result=1
elif [[ "${kind}" == "legacy" ]]; then
  python3 "${ROOT}/infra/backup_contract.py" unknown "${EVIDENCE}" "${started_at}" || result=1
fi
exit "${result}"
