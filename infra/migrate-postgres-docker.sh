#!/usr/bin/env bash
# Alembic against an explicitly allowed database URL only.
# Never uses a silent default URL. Production hosts/paths are always refused.
#
# Profiles:
#   BOOKER_MIGRATE_PROFILE=staging     — full staging_preflight (loopback :15432 / booker_staging*)
#   BOOKER_MIGRATE_PROFILE=local-docker — loopback :5432 local compose only (still reject production)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${BOOKER_MIGRATE_PROFILE:-staging}"

URL="${BOOKER_DATABASE_URL:-}"
if [[ -z "${URL}" ]]; then
  echo "migrate-postgres-docker: BOOKER_DATABASE_URL is required (no silent default)" >&2
  exit 2
fi

if [[ -n "${BOOKER_MIGRATE_ALLOW_URL:-}" && "${BOOKER_MIGRATE_ALLOW_URL}" != "${URL}" ]]; then
  echo "migrate-postgres-docker: BOOKER_MIGRATE_ALLOW_URL does not match BOOKER_DATABASE_URL" >&2
  exit 2
fi

# Always refuse known production markers regardless of profile.
case "${URL}" in
  *5.45.112.180*|*bukergo.ru*|*bookergo.ru*|*bukergo.online*|*/opt/booker/*|*sqlite:////opt/booker*)
    echo "migrate-postgres-docker: refusing production host/path" >&2
    exit 2
    ;;
esac

if [[ "${PROFILE}" == "staging" ]]; then
  export BOOKER_RUNTIME_ENV="${BOOKER_RUNTIME_ENV:-test}"
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-booker-staging}"
  export BOOKER_UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/tmp/booker-staging-uploads}"
  export BOOKER_PAYMENT_PROVIDER="${BOOKER_PAYMENT_PROVIDER:-stub}"
  export BOOKER_ALLOW_DEMO_SEED="${BOOKER_ALLOW_DEMO_SEED:-1}"
  python3 "${ROOT}/infra/staging_preflight.py" || exit 2
elif [[ "${PROFILE}" == "local-docker" ]]; then
  # Local docker-compose.yml postgres only — still no production.
  case "${URL}" in
    postgresql*://*@127.0.0.1:5432/*|postgresql*://*@localhost:5432/*) ;;
    *)
      echo "migrate-postgres-docker: local-docker profile requires 127.0.0.1|localhost:5432" >&2
      exit 2
      ;;
  esac
else
  echo "migrate-postgres-docker: unknown BOOKER_MIGRATE_PROFILE=${PROFILE}" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "migrate-postgres-docker: docker required" >&2
  exit 2
fi

exec docker run --rm --network host \
  -v "${ROOT}:/booker" -w /booker/apps/api \
  -e "BOOKER_DATABASE_URL=${URL}" \
  python:3.11-slim-bookworm \
  bash -c 'pip install -q -e ".[dev]" && python -m alembic upgrade head'
