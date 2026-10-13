#!/usr/bin/env bash
# Stage one immutable Booker release; the remote transaction owns switching and rollback.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${BOOKER_REMOTE:-root@5.45.112.180}"
PORT="${BOOKER_SSH_PORT:-2222}"
KEY="${BOOKER_SSH_KEY:-$HOME/.ssh/booker_deploy_key}"
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import secrets; print(secrets.token_hex(6))')"
SOURCE_SHA=UNKNOWN
if git -C "${ROOT}" rev-parse --verify HEAD >/dev/null 2>&1 &&
   [[ -z "$(git -C "${ROOT}" status --porcelain)" ]]; then
  SOURCE_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
fi

python3 "${ROOT}/scripts/check_secret_exposure.py" --source --deploy-payload

# The destination is a new, unpredictable release directory. No rsync touches current/data.
ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" \
  "test ! -L /opt/booker && test ! -L /opt/booker/releases && \
   install -d -m 755 /opt/booker/releases && \
   test ! -e /opt/booker/releases/${RELEASE_ID} && \
   install -d -m 755 /opt/booker/releases/${RELEASE_ID}"
rsync -az \
  --exclude-from="${ROOT}/infra/rsync-booker-excludes.txt" \
  -e "ssh -i ${KEY} -p ${PORT} -o ForwardX11=no -o StrictHostKeyChecking=accept-new" \
  "${ROOT}/" "${REMOTE}:/opt/booker/releases/${RELEASE_ID}/"

ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" \
  "python3 /opt/booker/releases/${RELEASE_ID}/infra/release_deploy.py \
   ${RELEASE_ID} --root /opt/booker --source-sha ${SOURCE_SHA}"
