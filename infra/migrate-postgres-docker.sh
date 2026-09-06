#!/usr/bin/env bash
# Alembic against local docker postgres when host Python lacks psycopg/_ctypes (broken pyenv build).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${BOOKER_DATABASE_URL:-postgresql+psycopg://booker:booker@127.0.0.1:5432/booker}"
exec docker run --rm --network host \
  -v "${ROOT}:/booker" -w /booker/apps/api \
  -e "BOOKER_DATABASE_URL=${URL}" \
  python:3.11-slim-bookworm \
  bash -c 'pip install -q -e ".[dev]" && python -m alembic upgrade head'
