#!/usr/bin/env bash
# Daily backup for the SQLite pilot or PostgreSQL.
# The v2 tar.gz archive contains a database payload, uploads/, and manifest.json.
set -euo pipefail

umask 077

BACKUP_ROOT="${BOOKER_BACKUP_DIR:-/var/backups/booker}"
UPLOAD_DIR="${BOOKER_UPLOAD_DIR:-/opt/booker/data/uploads}"
RETENTION_DAYS="${BOOKER_BACKUP_RETENTION_DAYS:-30}"
ALLOW_MISSING_UPLOAD_DIR="${BOOKER_ALLOW_MISSING_UPLOAD_DIR:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CREATED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DB_URL="${BOOKER_DATABASE_URL:-sqlite:////opt/booker/data/booker.db}"
STAGING=""
OUT=""
OUT_TMP=""
CHECKSUM_TMP=""
PAYLOAD=""
PUBLISHED="0"
OUT_OWNED="0"
PYTHON_BIN=""

fail() {
  echo "backup FAILED: $*" >&2
  exit 1
}

cleanup() {
  if [[ -n "${STAGING}" && -d "${STAGING}" ]]; then
    rm -rf -- "${STAGING}"
  fi
  if [[ -n "${OUT_TMP}" && -f "${OUT_TMP}" ]]; then
    rm -f -- "${OUT_TMP}"
  fi
  if [[ -n "${CHECKSUM_TMP}" && -f "${CHECKSUM_TMP}" ]]; then
    rm -f -- "${CHECKSUM_TMP}"
  fi
  if [[ "${PUBLISHED}" != "1" && "${OUT_OWNED}" == "1" && -n "${OUT}" ]]; then
    rm -f -- "${OUT}" "${OUT}.sha256"
  fi
}
trap cleanup EXIT INT TERM

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

select_python() {
  local candidate
  if [[ -n "${BOOKER_PYTHON:-}" ]]; then
    [[ -x "${BOOKER_PYTHON}" ]] || fail "BOOKER_PYTHON is not executable: ${BOOKER_PYTHON}"
    PYTHON_BIN="${BOOKER_PYTHON}"
    return
  fi
  candidate="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
  if [[ -x "${candidate}" ]]; then
    PYTHON_BIN="${candidate}"
    return
  fi
  PYTHON_BIN="$(command -v python3 || true)"
  [[ -n "${PYTHON_BIN}" ]] || fail "required command is unavailable: python3"
}

pg_url_for_libpq() {
  local url="$1"
  url="${url/postgresql+psycopg2/postgresql}"
  url="${url/postgres+psycopg2/postgresql}"
  url="${url/postgresql+psycopg/postgresql}"
  url="${url/postgres+psycopg/postgresql}"
  printf '%s\n' "${url}"
}

stage_uploads() {
  mkdir -p "${STAGING}/uploads"
  if [[ ! -d "${UPLOAD_DIR}" ]]; then
    if [[ "${ALLOW_MISSING_UPLOAD_DIR}" != "1" ]]; then
      fail "upload directory is missing: ${UPLOAD_DIR}; set BOOKER_ALLOW_MISSING_UPLOAD_DIR=1 only when an empty upload set is intentional"
    fi
    echo "backup warning: upload directory is missing; recording an explicitly empty uploads/" >&2
    return
  fi

  local unsafe_entry
  unsafe_entry="$(find "${UPLOAD_DIR}" -mindepth 1 ! -type f ! -type d -print -quit)"
  if [[ -n "${unsafe_entry}" ]]; then
    fail "uploads contain a symlink or special file, which is not archived safely: ${unsafe_entry}"
  fi
  cp -a -- "${UPLOAD_DIR}/." "${STAGING}/uploads/"
}

write_manifest() {
  local engine="$1"
  local payload="$2"
  local payload_format="$3"
  local metadata_path="$4"

  "${PYTHON_BIN}" - "${STAGING}" "${engine}" "${payload}" "${payload_format}" \
    "${CREATED_AT_UTC}" "${metadata_path}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

stage = Path(sys.argv[1])
engine = sys.argv[2]
payload = sys.argv[3]
payload_format = sys.argv[4]
created_at = sys.argv[5]
metadata_path = Path(sys.argv[6])

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata_path.unlink()

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()

files = {}
payload_path = stage / payload
if not payload_path.is_file():
    raise SystemExit(f"database payload missing before archive creation: {payload}")
files[payload] = digest(payload_path)

upload_files = sorted(path for path in (stage / "uploads").rglob("*") if path.is_file())
for path in upload_files:
    relative = path.relative_to(stage).as_posix()
    files[relative] = digest(path)

manifest = {
    "archive_format": "booker-backup",
    "archive_version": 2,
    "created_at_utc": created_at,
    "database_engine": engine,
    "database_payload": payload,
    "database_payload_format": payload_format,
    "files_sha256": files,
    "upload_file_count": len(upload_files),
    "upload_total_bytes": sum(path.stat().st_size for path in upload_files),
    "database": metadata,
}
(stage / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

create_sqlite_payload() {
  local metadata_path="${STAGING}/.database-metadata.json"
  "${PYTHON_BIN}" - "${DB_URL}" "${STAGING}/booker.db" "${metadata_path}" <<'PY'
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote, unquote

url = sys.argv[1]
destination = Path(sys.argv[2])
metadata_path = Path(sys.argv[3])

prefix = "sqlite:///"
if not url.startswith(prefix):
    raise SystemExit(f"unsupported SQLite URL: {url}")
raw_path = unquote(url[len(prefix):].split("?", 1)[0])
if not raw_path or raw_path == ":memory:":
    raise SystemExit("SQLite backup requires a file-backed database")
source_path = Path(raw_path).expanduser().resolve()
if not source_path.is_file():
    raise SystemExit(f"SQLite database does not exist: {source_path}")

source_uri = f"file:{quote(source_path.as_posix())}?mode=ro"
source = sqlite3.connect(source_uri, uri=True, timeout=30)
target = sqlite3.connect(destination)
try:
    source.backup(target)
finally:
    target.close()
    source.close()

connection = sqlite3.connect(f"file:{destination.as_posix()}?mode=ro", uri=True)
try:
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise SystemExit(f"SQLite integrity_check failed: {integrity!r}")
    foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
    if foreign_key_errors:
        raise SystemExit(f"SQLite foreign_key_check failed: {foreign_key_errors[:5]!r}")

    schema_rows = list(
        connection.execute(
            "SELECT type, name, tbl_name, COALESCE(sql, '') "
            "FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name"
        )
    )
    tables = sorted(row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ))
    if "users" not in tables:
        raise SystemExit("SQLite schema check failed: required users table is missing")

    alembic_revisions = []
    if "alembic_version" in tables:
        alembic_revisions = sorted(
            str(row[0]) for row in connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            )
        )

    key_tables = ["users", "organizations", "events", "bookings", "payments"]
    missing_key_tables = [table for table in key_tables if table not in tables]
    if missing_key_tables:
        raise SystemExit(
            f"SQLite schema check failed: required key tables are missing: {missing_key_tables!r}"
        )
    key_table_counts = {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in key_tables
    }
finally:
    connection.close()

schema_bytes = json.dumps(schema_rows, ensure_ascii=False, separators=(",", ":")).encode()
metadata = {
    "integrity_check": "ok",
    "foreign_key_check": "ok",
    "schema_fingerprint_kind": "sqlite_master_v1",
    "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
    "schema_tables": tables,
    "required_tables": key_tables,
    "key_table_counts": key_table_counts,
    "alembic_revisions": alembic_revisions,
    "alembic_state": (
        "versioned" if alembic_revisions else "empty" if "alembic_version" in tables else "absent"
    ),
}
metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
PY
  stage_uploads
  write_manifest "sqlite" "booker.db" "sqlite3" "${metadata_path}"
}

create_postgres_payload() {
  local pg_url
  local metadata_path="${STAGING}/.database-metadata.json"

  require_command pg_dump
  require_command pg_restore
  pg_url="$(pg_url_for_libpq "${DB_URL}")"

  # The Python argv below preserves the legacy URL-normalization invariant:
  # pg_dump "$(pg_url_for_libpq "${DB_URL}")"
  "${PYTHON_BIN}" - "${pg_url}" "${STAGING}/booker.dump" "${metadata_path}" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import psycopg
except ImportError as exc:
    raise SystemExit(
        "PostgreSQL backup requires psycopg; set BOOKER_PYTHON to the Booker venv Python"
    ) from exc

database_url = sys.argv[1]
dump_path = Path(sys.argv[2])
metadata_path = Path(sys.argv[3])
required_tables = [
    "users",
    "organizations",
    "events",
    "bookings",
    "payments",
    "alembic_version",
]

def fetch_rows(connection, query: str):
    return [list(row) for row in connection.execute(query).fetchall()]

def schema_descriptor(connection):
    return {
        "columns": fetch_rows(
            connection,
            """
            SELECT table_name, ordinal_position, column_name, data_type,
                   udt_schema, udt_name, is_nullable, column_default,
                   is_identity, identity_generation, is_generated,
                   generation_expression
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """,
        ),
        "constraints": fetch_rows(
            connection,
            """
            SELECT cls.relname, con.conname, con.contype::text,
                   pg_get_constraintdef(con.oid, true)
            FROM pg_catalog.pg_constraint AS con
            JOIN pg_catalog.pg_class AS cls ON cls.oid = con.conrelid
            JOIN pg_catalog.pg_namespace AS ns ON ns.oid = cls.relnamespace
            WHERE ns.nspname = 'public'
            ORDER BY cls.relname, con.conname
            """,
        ),
        "indexes": fetch_rows(
            connection,
            """
            SELECT tbl.relname, idx.relname, ind.indisprimary, ind.indisunique,
                   pg_get_indexdef(ind.indexrelid, 0, true)
            FROM pg_catalog.pg_index AS ind
            JOIN pg_catalog.pg_class AS tbl ON tbl.oid = ind.indrelid
            JOIN pg_catalog.pg_class AS idx ON idx.oid = ind.indexrelid
            JOIN pg_catalog.pg_namespace AS ns ON ns.oid = tbl.relnamespace
            WHERE ns.nspname = 'public'
            ORDER BY tbl.relname, idx.relname
            """,
        ),
        "sequences": fetch_rows(
            connection,
            """
            SELECT sequence_name, data_type, start_value, minimum_value,
                   maximum_value, increment, cycle_option
            FROM information_schema.sequences
            WHERE sequence_schema = 'public'
            ORDER BY sequence_name
            """,
        ),
        "enums": fetch_rows(
            connection,
            """
            SELECT typ.typname, enum.enumsortorder, enum.enumlabel
            FROM pg_catalog.pg_type AS typ
            JOIN pg_catalog.pg_enum AS enum ON enum.enumtypid = typ.oid
            JOIN pg_catalog.pg_namespace AS ns ON ns.oid = typ.typnamespace
            WHERE ns.nspname = 'public'
            ORDER BY typ.typname, enum.enumsortorder
            """,
        ),
    }

with psycopg.connect(database_url, autocommit=True) as connection:
    connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    committed = False
    try:
        snapshot_id = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--compress=6",
                "--no-owner",
                "--no-privileges",
                f"--snapshot={snapshot_id}",
                f"--file={dump_path}",
                database_url,
            ],
            check=True,
        )

        tables = [
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' ORDER BY tablename"
            ).fetchall()
        ]
        missing = [table for table in required_tables if table not in tables]
        if missing:
            raise SystemExit(
                f"PostgreSQL schema check failed: required tables are missing: {missing!r}"
            )
        revisions = [
            str(row[0])
            for row in connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).fetchall()
        ]
        if not revisions:
            raise SystemExit("PostgreSQL schema check failed: alembic_version is empty")
        key_table_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in required_tables
        }
        descriptor = schema_descriptor(connection)
        canonical_schema = json.dumps(
            descriptor,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        metadata = {
            "schema_fingerprint_kind": "postgres_catalog_v2",
            "schema_sha256": hashlib.sha256(canonical_schema).hexdigest(),
            "schema_descriptor": descriptor,
            "schema_tables": tables,
            "required_tables": required_tables,
            "key_table_counts": key_table_counts,
            "alembic_revisions": revisions,
            "alembic_state": "versioned",
            "snapshot_consistency": "pg_export_snapshot",
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str),
            encoding="utf-8",
        )
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            connection.execute("ROLLBACK")
PY
  pg_restore --list "${STAGING}/booker.dump" >/dev/null
  stage_uploads
  write_manifest "postgresql" "booker.dump" "postgres-custom" "${metadata_path}"
}

require_command tar
require_command sha256sum
require_command flock
select_python
[[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]] || fail "BOOKER_BACKUP_RETENTION_DAYS must be a non-negative integer"
mkdir -p -- "${BACKUP_ROOT}"
exec 9>"${BACKUP_ROOT}/.backup.lock"
flock -n 9 || fail "another Booker backup is already running"
STAGING="$(mktemp -d "${BACKUP_ROOT}/.staging-${STAMP}.XXXXXX")"

case "${DB_URL}" in
  sqlite:*)
    OUT="${BACKUP_ROOT}/booker-${STAMP}.tar.gz"
    PAYLOAD="booker.db"
    create_sqlite_payload
    ;;
  postgres:*|postgresql:*|postgres+*:*|postgresql+*:*)
    OUT="${BACKUP_ROOT}/booker-pg-${STAMP}.tar.gz"
    PAYLOAD="booker.dump"
    create_postgres_payload
    ;;
  *)
    fail "unsupported BOOKER_DATABASE_URL scheme"
    ;;
esac

[[ ! -e "${OUT}" && ! -e "${OUT}.sha256" ]] || fail "backup output already exists: ${OUT}"
OUT_TMP="${OUT}.partial.$$"
tar -czf "${OUT_TMP}" -C "${STAGING}" manifest.json "${PAYLOAD}" uploads
tar -tzf "${OUT_TMP}" >/dev/null
mv -- "${OUT_TMP}" "${OUT}"
OUT_TMP=""
OUT_OWNED="1"

archive_hash="$(sha256sum "${OUT}" | awk '{print $1}')"
CHECKSUM_TMP="${OUT}.sha256.partial.$$"
printf '%s  %s\n' "${archive_hash}" "$(basename "${OUT}")" >"${CHECKSUM_TMP}"
mv -- "${CHECKSUM_TMP}" "${OUT}.sha256"
CHECKSUM_TMP=""
PUBLISHED="1"

find "${BACKUP_ROOT}" -maxdepth 1 -type f \
  \( -name 'booker-*.tar.gz' -o -name 'booker-pg-*.tar.gz' \
     -o -name 'booker-*.tar.gz.sha256' -o -name 'booker-pg-*.tar.gz.sha256' \) \
  -mtime +"${RETENTION_DAYS}" -delete

echo "backup OK: ${OUT}"
echo "archive sha256: ${OUT}.sha256"
