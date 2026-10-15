#!/usr/bin/env bash
# Bring up isolated staging: preflight → compose → migrate → seed → API + web.
# Fail-closed. Never production. Does NOT count as staging score without owner ACK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="/tmp/booker-staging"
PREFLIGHT=(python3 "${ROOT}/infra/staging_preflight.py")

ENV_FILE="${BOOKER_STAGING_ENV_FILE:-}"
if [[ -z "${ENV_FILE}" ]]; then
  echo "staging-up: set BOOKER_STAGING_ENV_FILE to a secrets path outside Git" >&2
  echo "  example: cp infra/env.staging.example /tmp/booker-staging/secrets.env && edit passwords" >&2
  exit 2
fi
if [[ ! -e "${ENV_FILE}" ]]; then
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
GIT_SHA="$(git -C "${ROOT}" rev-parse HEAD)"

mkdir -p "${PID_DIR}"
chmod 700 "${PID_DIR}" || true

# Fail-closed before any write / migrate / seed
"${PREFLIGHT[@]}" --env-file "${ENV_FILE}"

# Port conflict detect — never kill foreign listeners
"${PREFLIGHT[@]}" --env-file "${ENV_FILE}" --check-ports "${API_PORT}" "${WEB_PORT}" || {
  # Re-run port-only messaging: if our own pidfiles hold the ports, stop cleanly first
  OWNED_STOP=0
  for name in api web; do
    if [[ -f "${PID_DIR}/${name}.pid" ]]; then
      old="$(tr -d '[:space:]' <"${PID_DIR}/${name}.pid" || true)"
      if [[ -n "${old}" ]] && [[ "${old}" =~ ^[0-9]+$ ]]; then
        if python3 -c "import sys; sys.path.insert(0,'${ROOT}/infra'); from staging_preflight import pid_owned_by_booker_staging; sys.exit(0 if pid_owned_by_booker_staging(int('${old}')) else 1)"; then
          OWNED_STOP=1
        fi
      fi
    fi
  done
  if [[ "${OWNED_STOP}" -eq 1 ]]; then
    echo "staging-up: stopping previous owned staging PIDs before rebind"
    bash "${ROOT}/infra/staging-down.sh" || true
    "${PREFLIGHT[@]}" --env-file "${ENV_FILE}" --check-ports "${API_PORT}" "${WEB_PORT}"
  else
    echo "staging-up: port conflict with foreign process — abort (no kill)" >&2
    exit 2
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: docker not available. Use make staging-sqlite-rehearsal for LOCAL only." >&2
  exit 2
fi

# Standalone compose file only — never merge with infra/docker-compose.yml
COMPOSE=(docker compose -f "${ROOT}/infra/docker-compose.staging.yml" --env-file "${ENV_FILE}")
export COMPOSE_PROJECT_NAME

echo "== compose config (secrets redacted) =="
CONFIG_OUT="$("${COMPOSE[@]}" config)"
CONFIG_RAW="${PID_DIR}/compose-config.raw.yml"
CONFIG_SAFE="${PID_DIR}/compose-config.yml"
umask 077
printf '%s\n' "${CONFIG_OUT}" >"${CONFIG_RAW}"
"${PREFLIGHT[@]}" --redact-file "${CONFIG_RAW}" >"${CONFIG_SAFE}"
rm -f "${CONFIG_RAW}"
# Log only redacted form
sed -n '1,80p' "${CONFIG_SAFE}"

if grep -E 'published: ["'\'']?5432["'\'']?' "${CONFIG_SAFE}" >/dev/null; then
  echo "staging-up: refusing compose config that publishes port 5432" >&2
  exit 2
fi
if ! grep -E 'published: ["'\'']?15432["'\'']?' "${CONFIG_SAFE}" >/dev/null; then
  echo "staging-up: expected published port 15432 missing from compose config" >&2
  exit 2
fi

# Refuse if known production-ish volumes exist under wrong project — do not delete them
if docker volume ls --format '{{.Name}}' | grep -qx 'booker_pg'; then
  echo "staging-up: note: volume booker_pg exists (dev compose); staging uses booker_pg_staging only"
fi

mkdir -p "${BOOKER_UPLOAD_DIR}"
chmod 700 "${BOOKER_UPLOAD_DIR}" || true
# Symlink escape after mkdir
python3 -c "
import sys
sys.path.insert(0, '${ROOT}/infra')
from staging_preflight import check_uploads
r = check_uploads('${BOOKER_UPLOAD_DIR}')
print(f'preflight {\"OK\" if r.ok else \"FAIL\"} [{r.code}] {r.detail}')
sys.exit(0 if r.ok else 2)
"

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

# Require migrate URL to match allow token — only after preflight PASS above
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

# Stop previous staging app processes ONLY if we own them (cmdline check)
stop_owned_pid() {
  local name="$1"
  local pidfile="${PID_DIR}/${name}.pid"
  if [[ ! -f "${pidfile}" ]]; then
    return 0
  fi
  local old
  old="$(tr -d '[:space:]' <"${pidfile}" || true)"
  rm -f "${pidfile}"
  if [[ -z "${old}" ]] || ! [[ "${old}" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  if ! kill -0 "${old}" 2>/dev/null; then
    return 0
  fi
  if python3 -c "import sys; sys.path.insert(0,'${ROOT}/infra'); from staging_preflight import pid_owned_by_booker_staging; sys.exit(0 if pid_owned_by_booker_staging(int('${old}')) else 1)"; then
    echo "staging-up: stopping owned ${name} pid ${old}"
    kill "${old}" || true
    sleep 1
    if kill -0 "${old}" 2>/dev/null; then
      kill -9 "${old}" || true
    fi
  else
    echo "staging-up: refuse to kill foreign pid ${old} from stale ${name}.pid" >&2
  fi
}
stop_owned_pid api
stop_owned_pid web

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
  echo "${GIT_SHA}" >"${PID_DIR}/api.sha"
)

for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null

echo "== web build bound to ${GIT_SHA} =="
WEB_DIR="${ROOT}/apps/web"
NEXT_DIR="${WEB_DIR}/.next"
NEED_BUILD=0
if [[ ! -d "${NEXT_DIR}" ]]; then
  NEED_BUILD=1
elif ! "${PREFLIGHT[@]}" --check-web-stamp "${GIT_SHA}" --web-next-dir "${NEXT_DIR}"; then
  echo "staging-up: unknown or mismatched .next — rebuilding for ${GIT_SHA}"
  rm -rf "${NEXT_DIR}"
  NEED_BUILD=1
fi
if [[ "${NEED_BUILD}" -eq 1 ]]; then
  (
    cd "${WEB_DIR}"
    NEXT_PUBLIC_API_URL="http://127.0.0.1:${API_PORT}" npm run build
  )
  python3 -c "
import sys
sys.path.insert(0, '${ROOT}/infra')
from staging_preflight import write_web_build_stamp
write_web_build_stamp('${GIT_SHA}')
print('web-build.sha written for ${GIT_SHA}')
"
fi

echo "== start web on 127.0.0.1:${WEB_PORT} =="
(
  cd "${WEB_DIR}"
  nohup env \
    NEXT_PUBLIC_API_URL="http://127.0.0.1:${API_PORT}" \
    BOOKER_INTERNAL_API_URL="http://127.0.0.1:${API_PORT}" \
    npm run start -- --hostname 127.0.0.1 --port "${WEB_PORT}" \
    >"${PID_DIR}/web.log" 2>&1 &
  echo $! >"${PID_DIR}/web.pid"
  echo "${GIT_SHA}" >"${PID_DIR}/web.sha"
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
echo "  SHA  ${GIT_SHA}"
echo "  stop: make staging-down"
