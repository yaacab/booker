#!/usr/bin/env bash
set -euo pipefail
# Повторный деплой Букера на VPS (тот же хост, что Белый Путь).
REMOTE="${BOOKER_REMOTE:-root@5.45.112.180}"
PORT="${BOOKER_SSH_PORT:-2222}"
KEY="${BOOKER_SSH_KEY:-$HOME/.ssh/booker_deploy_key}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

# Open-venues seed JSON (parent data/ is excluded above — sync explicitly)
ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" 'mkdir -p /opt/booker/data'
rsync -az \
  -e "ssh -i ${KEY} -p ${PORT} -o ForwardX11=no -o StrictHostKeyChecking=accept-new" \
  "${ROOT}/data/moscow_venues_open.json" "${REMOTE}:/opt/booker/data/moscow_venues_open.json"

ssh -i "${KEY}" -p "${PORT}" -o ForwardX11=no "${REMOTE}" 'bash -s' << 'REMOTE_SCRIPT'
set -euo pipefail
mkdir -p /opt/booker/data /var/www/letsencrypt /var/backups/booker
chmod +x /opt/booker/infra/backup-booker.sh /opt/booker/infra/restore-drill.sh 2>/dev/null || true
if [[ ! -f /etc/cron.d/booker-backup ]]; then
  cp /opt/booker/infra/cron-booker-backup.example /etc/cron.d/booker-backup
  chmod 644 /etc/cron.d/booker-backup
fi
BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db \
  /opt/booker/infra/backup-booker.sh || echo "backup skipped (non-fatal)"
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
curl -sS --retry 5 --retry-delay 1 --retry-connrefused http://127.0.0.1:8030/health
echo
cd /opt/booker/apps/api
BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db \
  /opt/booker/.venv/bin/python -m booker_api.seed_venues_moscow
# Founding artists: idempotent enrich only (no demo-user wipe)
BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db \
  /opt/booker/.venv/bin/python -c "from booker_api.db import SessionLocal; from booker_api.seed import enrich_catalog; db=SessionLocal(); print(enrich_catalog(db)); db.commit()"
# Seed runs as root; re-assert booker ownership of data afterwards
chown -R booker:booker /opt/booker/data
REMOTE_SCRIPT
