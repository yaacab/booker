#!/usr/bin/env bash
# LOCAL isolated SQLite staging rehearsal when Docker is unavailable.
# Level: LOCAL — does not close T10/O05 staging scores.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="${BOOKER_STAGING_REHEARSAL_DIR:-/tmp/booker-staging-rehearsal-${STAMP}}"
DB="${BASE}/booker.db"
UPLOADS="${BASE}/uploads"
BACKUP_DIR="${BASE}/backups"
RESTORE_DIR="${BASE}/restore"
EVIDENCE_DIR="${ROOT}/docs/ops/evidence"
# restore-drill requires the target path to not exist yet
mkdir -p "${UPLOADS}" "${BACKUP_DIR}" "${EVIDENCE_DIR}"
chmod 700 "${BASE}" "${UPLOADS}" "${BACKUP_DIR}" || true
rm -rf "${RESTORE_DIR}"

if [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
  PY="${ROOT}/apps/api/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY=python3
fi

export BOOKER_DATABASE_URL="sqlite:///${DB}"
export BOOKER_UPLOAD_DIR="${UPLOADS}"
export BOOKER_BACKUP_DIR="${BACKUP_DIR}"
export BOOKER_ALLOW_DEMO_SEED=1
export BOOKER_PAYMENT_PROVIDER=stub
export BOOKER_RUNTIME_ENV=test
export BOOKER_PYTHON="${PY}"

echo "== migrate (alembic upgrade head) =="
(
  cd "${ROOT}/apps/api"
  "${PY}" -m alembic upgrade head
)

echo "== seed =="
(
  cd "${ROOT}/apps/api"
  BOOKER_ALLOW_DEMO_SEED=1 "${PY}" -m booker_api.seed
)

echo "staging-rehearsal-${STAMP}" > "${UPLOADS}/rehearsal-marker.txt"

echo "== backup =="
STARTED=$(date +%s.%N)
bash "${ROOT}/infra/backup-booker.sh"
BACKUP_ARCHIVE="$(ls -1t "${BACKUP_DIR}"/booker-*.tar.gz "${BACKUP_DIR}"/booker-*.bke 2>/dev/null | head -1 || true)"
if [[ -z "${BACKUP_ARCHIVE}" ]]; then
  echo "FAIL: no backup archive in ${BACKUP_DIR}" >&2
  exit 1
fi

echo "== restore-drill =="
bash "${ROOT}/infra/restore-drill.sh" "${BACKUP_ARCHIVE}" "${RESTORE_DIR}"
ENDED=$(date +%s.%N)
RTO="$("${PY}" -c "print(round(float('${ENDED}')-float('${STARTED}'), 3))")"

REV="$("${PY}" -c "from sqlalchemy import create_engine, text; e=create_engine('sqlite:///${DB}');
c=e.connect();
print(c.execute(text('select version_num from alembic_version')).scalar())")"

MARKER_OK=FAIL
if [[ -f "${RESTORE_DIR}/uploads/rehearsal-marker.txt" ]] || \
   find "${RESTORE_DIR}" -name 'rehearsal-marker.txt' 2>/dev/null | grep -q .; then
  MARKER_OK=PASS
fi

GIT_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
OUT="${EVIDENCE_DIR}/2026-10-15-staging-sqlite-rehearsal.md"
{
  echo "# LOCAL staging SQLite rehearsal"
  echo
  echo "Date: ${STAMP}"
  echo "Level: **LOCAL** (not staging score T10/O05)"
  echo "Git SHA: ${GIT_SHA}"
  echo "Engine: SQLite"
  echo "Alembic revision (source DB): ${REV}"
  echo "Work dir: ${BASE}"
  echo "Backup archive: $(basename "${BACKUP_ARCHIVE}")"
  echo "Backup+restore wall seconds: ${RTO}"
  echo "Upload marker after restore: ${MARKER_OK}"
  echo "manual_block: preserved (schema-release-manifest not stamped)"
  echo
  echo "## Result"
  echo
  echo "PASS local rehearsal if restore-drill exit 0 and marker ${MARKER_OK}=PASS."
  echo "Does **not** authorize production. Does **not** close staging criteria without owner ACK."
} > "${OUT}"

echo "evidence written: ${OUT}"
echo "RTO_seconds=${RTO} revision=${REV} marker=${MARKER_OK}"
