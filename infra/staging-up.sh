#!/usr/bin/env bash
# Bring up isolated staging: preflight → compose → migrate → seed → API + web.
# Fail-closed. Never production. Does NOT count as staging score without owner ACK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ENV_FILE="${BOOKER_STAGING_ENV_FILE:-}"
if [[ -z "${ENV_FILE}" ]]; then
  echo "staging-up: set BOOKER_STAGING_ENV_FILE to a secrets path outside Git" >&2
  echo "  example: cp infra/env.staging.example /tmp/booker-staging/secrets.env && edit passwords" >&2
  exit 2
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "staging-up: env file not found: ${ENV_FILE}" >&2
  exit 2
fi
case "${ENV_FILE}" in
  /opt/booker/*|/etc/booker/*)
    echo "staging-up: refusing production env path ${ENV_FILE}" >&2
    exit 2
    ;;
esac

# Load secrets into environment (no print of values)
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"
export BOOKER_RUNTIME_ENV="${BOOKER_RUNTIME_ENV:-test}"
export BOOKER_PAYMENT_PROVIDER="${BOOKER_PAYMENT_PROVIDER:-stub}"
export BOOKER_ALLOW_DEMO_SEED="${BOOKER_ALLOW_DEMO_SEED:-1}"
export BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/tmp/booker-staging-uploads}"
API_PORT="${BOOKER_STAGING_API_PORT:-18080}"
WEB_PORT="${BOOKER_STAGING_WEB_PORT:-13000}"

# Fail-closed before any write
python3 "${ROOT}/infra/staging_preflight.py" --env-file "${ENV_FILE}"

if ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: docker not available. Use make staging-sqlite-rehearsal for LOCAL only." >&2
  exit 2
fi

# Standalone compose file only — never merge with infra/docker-compose.yml
COMPOSE=(docker compose -f "${ROOT}/infra/docker-compose.staging.yml" --env-file "${ENV_FILE}")
export COMPOSE_PROJECT_NAME

echo "== compose config (verify ports / no inherited 5432) =="
CONFIG_OUT="$("${COMPOSE[@]}" config)"
echo "${CONFIG_OUT}" | tee /tmp/booker-staging-compose-config.yml >/dev/null
if echo "${CONFIG_OUT}" | grep -E 'published: ["'\'']?5432["'\'']?|0\.0\.0\.0:5432|:6379' >/dev/null; then
  # allow 16379 but not bare 6379 / 5432
  if echo "${CONFIG_OUT}" | grep -E 'published: ["'\'']?5432["'\'']?' >/dev/null; then
    echo "staging-up: refusing compose config that publishes port 5432" >&2
    exit 2
  fi
fi
if ! echo "${CONFIG_OUT}" | grep -E 'published: ["'\'']?15432["'\'']?' >/dev/null; then
  echo "staging-up: expected published port 15432 missing from compose config" >&2
  exit 2
fi

# Refuse if known production-ish volumes exist under wrong project — do not delete them
if docker volume ls --format '{{.Name}}' | grep -qx 'booker_pg'; then
  echo "staging-up: note: volume booker_pg exists (dev compose); staging uses booker_pg_staging only"
fi

mkdir -p "${BOOKER_UPLOAD_DIR}"
chmod 700 "${BOOKER_UPLOAD_DIR}" || true

echo "== compose up =="
"${COMPOSE[@]}" up -d

echo "Waiting for postgres..."
for i in $(seq 1 40); do
  if "${COMPOSE[@]}" exec -T postgres \
    pg_isready -U "${BOOKER_STAGING_PGUSER}" -d "${BOOKER_STAGING_PGDATABASE}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Require migrate URL to match allow token
export BOOKER_MIGRATE_ALLOW_URL="${BOOKER_DATABASE_URL}"
bash "${ROOT}/infra/migrate-postgres-docker.sh"

if [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
  PY="${ROOT}/apps/api/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY=python3
fi

echo "== seed (demo only, runtime=test) =="
(
  cd "${ROOT}/apps/api"
  BOOKER_ALLOW_DEMO_SEED=1 \
    BOOKER_DATABASE_URL="${BOOKER_DATABASE_URL}" \
    BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR}" \
    BOOKER_RUNTIME_ENV="${BOOKER_RUNTIME_ENV}" \
    BOOKER_PAYMENT_PROVIDER=stub \
    "${PY}" -m booker_api.seed
)

# Stop previous staging app processes if we own the pidfiles
PID_DIR="/tmp/booker-staging"
mkdir -p "${PID_DIR}"
for name in api web; do
  if [[ -f "${PID_DIR}/${name}.pid" ]]; then
    old="$(cat "${PID_DIR}/${name}.pid" || true)"
    if [[ -n "${old}" ]] && kill -0 "${old}" 2>/dev/null; then
      kill "${old}" || true
      sleep 1
    fi
    rm -f "${PID_DIR}/${name}.pid"
  fi
done

echo "== start API on 127.0.0.1:${API_PORT} =="
(
  cd "${ROOT}/apps/api"
  nohup env \
    BOOKER_DATABASE_URL="${BOOKER_DATABASE_URL}" \
    BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR}" \
    BOOKER_RUNTIME_ENV="${BOOKER_RUNTIME_ENV}" \
    BOOKER_PAYMENT_PROVIDER=stub \
    BOOKER_CORS_ORIGINS="${BOOKER_CORS_ORIGINS}" \
    BOOKER_ALLOW_DEMO_SEED=1 \
    "${PY}" -m uvicorn booker_api.main:app --host 127.0.0.1 --port "${API_PORT}" \
    >"${PID_DIR}/api.log" 2>&1 &
  echo $! >"${PID_DIR}/api.pid"
)

for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null

echo "== start web on 127.0.0.1:${WEB_PORT} =="
(
  cd "${ROOT}/apps/web"
  if [[ ! -d .next ]]; then
    NEXT_PUBLIC_API_URL="http://127.0.0.1:${API_PORT}" npm run build
  fi
  nohup env \
    NEXT_PUBLIC_API_URL="http://127.0.0.1:${API_PORT}" \
    BOOKER_INTERNAL_API_URL="http://127.0.0.1:${API_PORT}" \
    npm run start -- --hostname 127.0.0.1 --port "${WEB_PORT}" \
    >"${PID_DIR}/web.log" 2>&1 &
  echo $! >"${PID_DIR}/web.pid"
)

for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null; then
    break
  fi
  sleep 1
done

echo "staging harness READY (LOCAL level — not score T10/T12 without owner ACK)"
echo "  API  http://127.0.0.1:${API_PORT}/health"
echo "  WEB  http://127.0.0.1:${WEB_PORT}/"
echo "  SHA  $(git -C "${ROOT}" rev-parse HEAD)"
echo "  stop: make staging-down"
