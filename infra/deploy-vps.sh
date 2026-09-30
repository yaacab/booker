#!/usr/bin/env bash
set -euo pipefail

# Legacy incident-only deployment path. Normal releases must follow
# docs/ops/DESIGN_RELEASE_RUNBOOK.md.
readonly REQUIRED_LEGACY_ACK="I_UNDERSTAND_THIS_IS_AN_EMERGENCY_PRODUCTION_DEPLOY"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
  echo "legacy production deploy BLOCKED: $*" >&2
  exit 64
}

if [[ "${BOOKER_LEGACY_DEPLOY_ACK:-}" != "${REQUIRED_LEGACY_ACK}" ]]; then
  fail "set BOOKER_LEGACY_DEPLOY_ACK=${REQUIRED_LEGACY_ACK} only for an authorized incident; use docs/ops/DESIGN_RELEASE_RUNBOOK.md for normal releases"
fi

RELEASE_SHA="${BOOKER_RELEASE_SHA:-}"
[[ "${RELEASE_SHA}" =~ ^[0-9a-f]{40}$ ]] || \
  fail "BOOKER_RELEASE_SHA must be the full 40-character lowercase commit SHA"
git -C "${ROOT}" cat-file -e "${RELEASE_SHA}^{commit}" 2>/dev/null || \
  fail "BOOKER_RELEASE_SHA is not a commit in this checkout"
CURRENT_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
[[ "${CURRENT_SHA}" == "${RELEASE_SHA}" ]] || \
  fail "BOOKER_RELEASE_SHA must match the checked-out HEAD (${CURRENT_SHA})"
[[ -z "$(git -C "${ROOT}" status --porcelain=v1 --untracked-files=all)" ]] || \
  fail "the checkout must be clean, including untracked files"

# Повторный аварийный деплой Букера на VPS.
REMOTE="${BOOKER_REMOTE:-root@5.45.112.180}"
PORT="${BOOKER_SSH_PORT:-2222}"
KEY="${BOOKER_SSH_KEY:-$HOME/.ssh/booker_deploy_key}"

# The existing production backup tool must succeed before rsync changes any
# live source. Missing tooling, unsupported database configuration, corrupt
# data, or an archive validation failure blocks the emergency deployment.
if ! ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" \
  'BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db /opt/booker/infra/backup-booker.sh'; then
  echo "backup failed; deployment aborted before live source was changed" >&2
  exit 1
fi

rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.cursor/' \
  --exclude '*.db' \
  --exclude 'data/' \
  --exclude 'apps/web/node_modules/' \
  --exclude 'apps/web/.next/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  -e "ssh -i ${KEY} -p ${PORT} -o ForwardX11=no -o StrictHostKeyChecking=accept-new" \
  "${ROOT}/" "${REMOTE}:/opt/booker/"

ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" 'bash -s' << 'REMOTE_SCRIPT'
set -euo pipefail
mkdir -p /opt/booker/data /var/www/letsencrypt /var/backups/booker
chmod +x /opt/booker/infra/backup-booker.sh /opt/booker/infra/restore-drill.sh 2>/dev/null || true
if [[ ! -f /etc/cron.d/booker-backup ]]; then
  cp /opt/booker/infra/cron-booker-backup.example /etc/cron.d/booker-backup
  chmod 644 /etc/cron.d/booker-backup
fi
/opt/booker/.venv/bin/pip install -e "/opt/booker/apps/api" -q
cd /opt/booker/apps/web
npm ci --silent
export NEXT_PUBLIC_API_URL=/api
export NEXT_PUBLIC_SITE_URL=https://bukergo.ru
# Event Studio Map: default OFF (omit or 0). Set =1 only after rebuild when enabling.
# export NEXT_PUBLIC_EVENT_STUDIO_MAP_V1=1
export BOOKER_INTERNAL_API_URL=http://127.0.0.1:8030
# Snapshot the live build before replacing it. Failed/interrupted deploys must not
# leave booker-web without BUILD_ID (nginx 502 crash-loop).
if [[ -d .next && -f .next/BUILD_ID ]]; then
  rm -rf .next.bak
  cp -a .next .next.bak
fi
systemctl stop booker-web || true
pkill -f "/opt/booker/apps/web/node_modules/.bin/next" || true
sleep 1
if ! npm run build; then
  echo "web build failed — restoring previous .next" >&2
  rm -rf .next
  if [[ -d .next.bak ]]; then
    mv .next.bak .next
  fi
  systemctl start booker-web || true
  exit 1
fi
rm -rf .next.bak
# Dedicated service user for systemd units (idempotent)
if ! id -u booker >/dev/null 2>&1; then
  useradd --system --home /var/lib/booker --create-home --shell /usr/sbin/nologin booker
fi
chown -R booker:booker /opt/booker/data /opt/booker/apps/web/.next
[[ ! -d /opt/booker/apps/api/data ]] || chown -R booker:booker /opt/booker/apps/api/data
cp /opt/booker/infra/systemd/booker-api.service /etc/systemd/system/
cp /opt/booker/infra/systemd/booker-web.service /etc/systemd/system/
cp /opt/booker/infra/nginx/bukergo.ru.conf /etc/nginx/sites-available/bukergo.ru.conf
ln -sfn /etc/nginx/sites-available/bukergo.ru.conf /etc/nginx/sites-enabled/bukergo.ru.conf
nginx -t
systemctl daemon-reload
systemctl restart booker-api booker-web
sleep 2
nginx -s reload
systemctl is-active booker-api booker-web
curl --fail --silent --show-error --retry 5 --retry-delay 1 --retry-connrefused \
  http://127.0.0.1:8030/health
echo
REMOTE_SCRIPT
