#!/usr/bin/env bash
# Bring up isolated staging data plane (Postgres+Redis) and migrate+seed.
# SAFE LOCAL / STAGING MUTATION only on loopback. Never uses production host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "${ROOT}/infra/docker-compose.yml" -f "${ROOT}/infra/docker-compose.staging.yml" --profile staging)
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"

if ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: docker not available on this host" >&2
  echo "Use SQLite fallback: make staging-sqlite-rehearsal" >&2
  exit 2
fi

mkdir -p /tmp/booker-staging-uploads
chmod 700 /tmp/booker-staging-uploads || true

"${COMPOSE[@]}" up -d
echo "Waiting for postgres health..."
for i in $(seq 1 40); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U booker_staging -d booker_staging >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export BOOKER_DATABASE_URL="${BOOKER_DATABASE_URL:-postgresql+psycopg://booker_staging:booker_staging@127.0.0.1:15432/booker_staging}"
export BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/tmp/booker-staging-uploads}"
export BOOKER_ALLOW_DEMO_SEED=1
export BOOKER_PAYMENT_PROVIDER=stub
export BOOKER_RUNTIME_ENV=test

bash "${ROOT}/infra/migrate-postgres-docker.sh"
(
  cd "${ROOT}/apps/api"
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  elif [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
    PY="${ROOT}/apps/api/.venv/bin/python"
  else
    PY=python3
  fi
  BOOKER_ALLOW_DEMO_SEED=1 BOOKER_DATABASE_URL="${BOOKER_DATABASE_URL}" \
    BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR}" \
    "${PY}" -m booker_api.seed
)

echo "staging data plane READY project=${COMPOSE_PROJECT_NAME} db=${BOOKER_DATABASE_URL}"
echo "health: start API with env.staging.example then curl http://127.0.0.1:18080/health"
