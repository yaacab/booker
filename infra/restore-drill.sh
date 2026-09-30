#!/usr/bin/env bash
# Restore and verify a Booker backup in an isolated location.
# PostgreSQL restore additionally requires an explicitly confirmed empty target DB.
set -euo pipefail

# A caller may invoke this script with `bash -x`; never trace credential
# handling into logs. Capture the restore URL in a non-exported shell variable
# before starting any child process, then remove the inherited environment key.
set +x

umask 077

RESTORE_DATABASE_URL="${BOOKER_RESTORE_DATABASE_URL-}"
export -n RESTORE_DATABASE_URL
unset BOOKER_RESTORE_DATABASE_URL

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <backup.tar.gz> [new_restore_dir]" >&2
  exit 1
fi

BACKUP="$1"
RESTORE_DIR="${2:-/tmp/booker-restore-drill}"
WORK_ROOT=""
EXTRACT_DIR=""
SIDECAR_STATUS="absent"
MANIFEST_MODE="legacy"
ENGINE=""
PAYLOAD=""
PAYLOAD_FORMAT=""
PYTHON_BIN=""
POSTGRES_SAFE_URL=""
POSTGRES_SAFE_URL_FILE=""
PGPASS_FILE=""

fail() {
  echo "restore drill FAILED: $*" >&2
  exit 1
}

cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if [[ -n "${WORK_ROOT}" && -d "${WORK_ROOT}" ]]; then
    if ! rm -rf -- "${WORK_ROOT}"; then
      echo "restore drill FAILED: could not remove private work directory: ${WORK_ROOT}" >&2
      [[ "${status}" -ne 0 ]] || status=1
    fi
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

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

prepare_postgres_connection() {
  local secret_url_path="${WORK_ROOT}/.restore-database-url"
  local credential_mode_path="${WORK_ROOT}/.restore-credential-mode"
  local credential_mode=""

  [[ -n "${RESTORE_DATABASE_URL}" ]] \
    || fail "PostgreSQL drill requires BOOKER_RESTORE_DATABASE_URL; BOOKER_DATABASE_URL is deliberately ignored"
  [[ "${RESTORE_DATABASE_URL}" == postgres:* \
      || "${RESTORE_DATABASE_URL}" == postgresql:* \
      || "${RESTORE_DATABASE_URL}" == postgres+*:* \
      || "${RESTORE_DATABASE_URL}" == postgresql+*:* ]] \
    || fail "BOOKER_RESTORE_DATABASE_URL must use a PostgreSQL scheme"

  POSTGRES_SAFE_URL_FILE="${WORK_ROOT}/.restore-connection-url"
  PGPASS_FILE="${WORK_ROOT}/.pgpass"

  # `printf` is a Bash builtin, so the password is never placed in a child
  # argv. The URL file lives in mktemp's private directory under umask 077.
  if ! printf '%s' "${RESTORE_DATABASE_URL}" >"${secret_url_path}"; then
    fail "could not stage PostgreSQL restore credentials"
  fi
  RESTORE_DATABASE_URL=""
  chmod 600 -- "${secret_url_path}"

  "${PYTHON_BIN}" - "${secret_url_path}" "${POSTGRES_SAFE_URL_FILE}" \
    "${PGPASS_FILE}" "${credential_mode_path}" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

secret_path = Path(sys.argv[1])
safe_url_path = Path(sys.argv[2])
pgpass_path = Path(sys.argv[3])
mode_path = Path(sys.argv[4])


def write_private(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
    path.chmod(0o600)


try:
    raw_url = secret_path.read_text(encoding="utf-8")
finally:
    secret_path.unlink(missing_ok=True)

if not raw_url or any(character in raw_url for character in ("\x00", "\r", "\n")):
    raise SystemExit("BOOKER_RESTORE_DATABASE_URL is empty or contains a forbidden control character")

parts = urlsplit(raw_url)
scheme_aliases = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "postgres+psycopg": "postgresql",
    "postgresql+psycopg": "postgresql",
    "postgres+psycopg2": "postgresql",
    "postgresql+psycopg2": "postgresql",
}
scheme = scheme_aliases.get(parts.scheme.lower())
if scheme is None:
    raise SystemExit("BOOKER_RESTORE_DATABASE_URL must use a supported PostgreSQL scheme")
if parts.fragment:
    raise SystemExit("BOOKER_RESTORE_DATABASE_URL must not contain a URL fragment")

# Keep the authority byte-for-byte except for its password. Using rsplit('@')
# safely handles percent-encoded '@' in credentials and IPv6 host colons.
safe_netloc = parts.netloc
authority_password = None
if "@" in parts.netloc:
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    if ":" in userinfo:
        encoded_user, encoded_password = userinfo.split(":", 1)
        authority_password = unquote(encoded_password)
        safe_netloc = f"{encoded_user}@{hostinfo}"

query_items = parse_qsl(parts.query, keep_blank_values=True)
query_passwords = [value for key, value in query_items if key.lower() == "password"]
if any(key.lower() == "sslpassword" for key, _ in query_items):
    raise SystemExit(
        "sslpassword must not be embedded in BOOKER_RESTORE_DATABASE_URL; "
        "supply it out of band with libpq configuration"
    )

password_values = ([] if authority_password is None else [authority_password]) + query_passwords
if password_values and any(value != password_values[0] for value in password_values[1:]):
    raise SystemExit("BOOKER_RESTORE_DATABASE_URL contains conflicting passwords")
password = password_values[0] if password_values else None

safe_query_items = []
effective_parameters = {}
for key, value in query_items:
    lowered = key.lower()
    if lowered == "password":
        continue
    if lowered == "passfile" and password is not None:
        # The temporary PGPASSFILE must be the only password source when the
        # URL itself supplied a password.
        continue
    safe_query_items.append((key, value))
    if lowered in {"host", "port", "dbname", "user"}:
        effective_parameters[lowered] = value

safe_url = urlunsplit(
    (
        scheme,
        safe_netloc,
        parts.path,
        urlencode(safe_query_items, doseq=True),
        "",
    )
)
write_private(safe_url_path, safe_url + "\n")

if password is None:
    write_private(mode_path, "external\n")
    raise SystemExit(0)

try:
    authority_port = parts.port
except ValueError as exc:
    raise SystemExit(f"invalid PostgreSQL port: {exc}") from exc

host = effective_parameters.get("host")
if host is None:
    host = unquote(parts.hostname) if parts.hostname else "*"
port = effective_parameters.get("port") or (
    str(authority_port) if authority_port is not None else "*"
)
database = effective_parameters.get("dbname")
if database is None:
    database = unquote(parts.path[1:] if parts.path.startswith("/") else parts.path) or "*"
user = effective_parameters.get("user")
if user is None:
    user = unquote(parts.username) if parts.username is not None else "*"

# Multi-host libpq URLs select one host at runtime. Wildcards keep the private,
# process-scoped password file valid for that failover without exposing it.
if "," in host:
    host = "*"
if "," in port:
    port = "*"


def pgpass_escape(value: str) -> str:
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise SystemExit("PostgreSQL credentials contain a forbidden control character")
    return value.replace("\\", "\\\\").replace(":", "\\:")


pgpass_line = ":".join(
    pgpass_escape(value) for value in (host, port, database, user, password)
)
write_private(pgpass_path, pgpass_line + "\n")
write_private(mode_path, "pgpass\n")
PY

  [[ -f "${POSTGRES_SAFE_URL_FILE}" ]] \
    || fail "could not create a password-free PostgreSQL connection URL"
  IFS= read -r POSTGRES_SAFE_URL <"${POSTGRES_SAFE_URL_FILE}" \
    || fail "could not read the password-free PostgreSQL connection URL"
  IFS= read -r credential_mode <"${credential_mode_path}" \
    || fail "could not read PostgreSQL credential mode"
  [[ -n "${POSTGRES_SAFE_URL}" ]] || fail "password-free PostgreSQL connection URL is empty"

  case "${credential_mode}" in
    pgpass)
      [[ -f "${PGPASS_FILE}" ]] || fail "temporary PostgreSQL password file is missing"
      [[ "$(stat -c '%a' -- "${PGPASS_FILE}")" == "600" ]] \
        || fail "temporary PostgreSQL password file must have mode 0600"
      export PGPASSFILE="${PGPASS_FILE}"
      # An inherited PGPASSWORD would take precedence over PGPASSFILE and
      # silently change the credentials used for this destructive operation.
      unset PGPASSWORD
      ;;
    external)
      PGPASS_FILE=""
      ;;
    *)
      fail "unsupported PostgreSQL credential mode"
      ;;
  esac
}

publish_restore_dir() {
  mkdir -p -- "$(dirname "${RESTORE_DIR}")"
  [[ ! -e "${RESTORE_DIR}" ]] \
    || fail "restore destination appeared during the drill; refusing to merge with it: ${RESTORE_DIR}"
  mv -- "${EXTRACT_DIR}" "${RESTORE_DIR}"
  EXTRACT_DIR=""
}

[[ -f "${BACKUP}" ]] || fail "archive is missing or is not a regular file: ${BACKUP}"
[[ "${RESTORE_DIR}" != "/" && -n "${RESTORE_DIR}" ]] || fail "unsafe restore destination"
[[ ! -e "${RESTORE_DIR}" ]] \
  || fail "restore destination must not exist; use a new empty path: ${RESTORE_DIR}"

require_command sha256sum
select_python
WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/booker-restore.XXXXXX")"
EXTRACT_DIR="${WORK_ROOT}/extracted"
mkdir -p "${EXTRACT_DIR}"
cp -- "${BACKUP}" "${WORK_ROOT}/archive.tar.gz"

if [[ -f "${BACKUP}.sha256" ]]; then
  expected_hash=""
  if ! expected_hash="$(awk 'NF { count += 1; value = $1 } END { if (count != 1) exit 1; print value }' "${BACKUP}.sha256")"; then
    fail "archive checksum sidecar must contain exactly one non-empty record: ${BACKUP}.sha256"
  fi
  [[ "${expected_hash}" =~ ^[0-9a-fA-F]{64}$ ]] \
    || fail "archive checksum sidecar contains an invalid SHA-256"
  actual_hash="$(sha256sum "${WORK_ROOT}/archive.tar.gz" | awk '{print $1}')"
  [[ "${actual_hash,,}" == "${expected_hash,,}" ]] \
    || fail "archive SHA-256 does not match ${BACKUP}.sha256"
  SIDECAR_STATUS="verified"
fi

"${PYTHON_BIN}" - "${WORK_ROOT}/archive.tar.gz" "${EXTRACT_DIR}" <<'PY'
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2])
allowed_roots = {"booker.db", "booker.dump", "manifest.json", "uploads"}
seen = set()

def normalize(name: str) -> PurePosixPath | None:
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe archive member path: {name!r}")
    if not path.parts or path.parts[0] not in allowed_roots:
        raise SystemExit(f"unexpected archive member: {name!r}")
    if path.parts[0] in {"booker.db", "booker.dump", "manifest.json"} and len(path.parts) != 1:
        raise SystemExit(f"invalid database or manifest member path: {name!r}")
    return path

with tarfile.open(archive_path, "r:gz") as archive:
    members = []
    for member in archive.getmembers():
        normalized = normalize(member.name)
        if normalized is None:
            if member.isdir():
                continue
            raise SystemExit(f"unexpected root archive member: {member.name!r}")
        key = normalized.as_posix()
        if key in seen:
            raise SystemExit(f"duplicate archive member: {key!r}")
        seen.add(key)
        if not (member.isdir() or member.isfile()):
            raise SystemExit(f"links and special files are forbidden in backups: {key!r}")
        members.append((member, normalized))

    for member, normalized in members:
        target = destination.joinpath(*normalized.parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        source = archive.extractfile(member)
        if source is None:
            raise SystemExit(f"cannot read archive member: {normalized.as_posix()!r}")
        with source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o600)
PY

[[ -d "${EXTRACT_DIR}/uploads" ]] || fail "uploads directory is missing in archive"

if [[ -f "${EXTRACT_DIR}/manifest.json" ]]; then
  MANIFEST_MODE="v2"
  "${PYTHON_BIN}" - "${EXTRACT_DIR}" "${WORK_ROOT}/archive-info" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

root = Path(sys.argv[1])
info_path = Path(sys.argv[2])
manifest_path = root / "manifest.json"
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid manifest.json: {exc}")

if manifest.get("archive_format") != "booker-backup" or manifest.get("archive_version") != 2:
    raise SystemExit("unsupported backup manifest format/version")
engine = manifest.get("database_engine")
payload = manifest.get("database_payload")
payload_format = manifest.get("database_payload_format")
expected = {
    "sqlite": ("booker.db", "sqlite3"),
    "postgresql": ("booker.dump", "postgres-custom"),
}
if engine not in expected or (payload, payload_format) != expected[engine]:
    raise SystemExit("manifest database engine/payload combination is invalid")

files = manifest.get("files_sha256")
if not isinstance(files, dict) or payload not in files:
    raise SystemExit("manifest files_sha256 is missing the database payload")

actual_files = {
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file() and path != manifest_path
}
if actual_files != set(files):
    missing = sorted(set(files) - actual_files)
    extra = sorted(actual_files - set(files))
    raise SystemExit(f"manifest file set mismatch: missing={missing!r}, extra={extra!r}")

for relative, expected_hash in files.items():
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SystemExit(f"unsafe path in manifest: {relative!r}")
    if path.parts[0] not in {payload, "uploads"}:
        raise SystemExit(f"unexpected path in manifest: {relative!r}")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise SystemExit(f"invalid SHA-256 in manifest for {relative!r}")
    digest = hashlib.sha256()
    with (root / relative).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_hash:
        raise SystemExit(f"SHA-256 mismatch for {relative!r}")

upload_files = [path for path in (root / "uploads").rglob("*") if path.is_file()]
if manifest.get("upload_file_count") != len(upload_files):
    raise SystemExit("upload file count does not match manifest")
if manifest.get("upload_total_bytes") != sum(path.stat().st_size for path in upload_files):
    raise SystemExit("upload byte count does not match manifest")
if not isinstance(manifest.get("database"), dict):
    raise SystemExit("database metadata is missing from manifest")

info_path.write_text(f"{engine}\n{payload}\n{payload_format}\n", encoding="utf-8")
PY
  ENGINE="$(sed -n '1p' "${WORK_ROOT}/archive-info")"
  PAYLOAD="$(sed -n '2p' "${WORK_ROOT}/archive-info")"
  PAYLOAD_FORMAT="$(sed -n '3p' "${WORK_ROOT}/archive-info")"
  [[ "${SIDECAR_STATUS}" == "verified" ]] \
    || fail "v2 archive requires its matching .sha256 sidecar"
else
  echo "restore drill warning: legacy archive has no manifest or internal file checksums" >&2
  if [[ -f "${EXTRACT_DIR}/booker.db" && ! -e "${EXTRACT_DIR}/booker.dump" ]]; then
    ENGINE="sqlite"
    PAYLOAD="booker.db"
    PAYLOAD_FORMAT="sqlite3"
  elif [[ -f "${EXTRACT_DIR}/booker.dump" && ! -e "${EXTRACT_DIR}/booker.db" ]]; then
    ENGINE="postgresql"
    PAYLOAD="booker.dump"
    PAYLOAD_FORMAT="legacy-undetected"
  else
    fail "legacy archive must contain exactly one of booker.db or booker.dump"
  fi
fi

verify_sqlite() {
  "${PYTHON_BIN}" - "${EXTRACT_DIR}/booker.db" \
    "$([[ "${MANIFEST_MODE}" == "v2" ]] && printf '%s' "${EXTRACT_DIR}/manifest.json")" \
    "${WORK_ROOT}/database-status" <<'PY'
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

database_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2]) if sys.argv[2] else None
status_path = Path(sys.argv[3])
connection = sqlite3.connect(
    f"file:{quote(database_path.as_posix())}?mode=ro", uri=True
)
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
        raise SystemExit("required users table is missing")
    connection.execute("SELECT COUNT(*) FROM users").fetchone()

    alembic_revisions = []
    if "alembic_version" in tables:
        alembic_revisions = sorted(
            str(row[0]) for row in connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            )
        )

    if manifest_path:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metadata = manifest["database"]
        if metadata.get("schema_fingerprint_kind") != "sqlite_master_v1":
            raise SystemExit("unsupported SQLite schema fingerprint")
        schema_bytes = json.dumps(
            schema_rows, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if hashlib.sha256(schema_bytes).hexdigest() != metadata.get("schema_sha256"):
            raise SystemExit("SQLite schema SHA-256 does not match manifest")
        if tables != metadata.get("schema_tables"):
            raise SystemExit("SQLite table set does not match manifest")
        if alembic_revisions != metadata.get("alembic_revisions"):
            raise SystemExit("SQLite Alembic revision does not match manifest")
        expected_alembic_state = (
            "versioned"
            if alembic_revisions
            else "empty"
            if "alembic_version" in tables
            else "absent"
        )
        if expected_alembic_state != metadata.get("alembic_state"):
            raise SystemExit("SQLite Alembic state does not match manifest")
        for table in metadata.get("required_tables", []):
            if table not in tables:
                raise SystemExit(f"required key table is missing: {table}")
        for table, expected_count in metadata.get("key_table_counts", {}).items():
            if table not in tables:
                raise SystemExit(f"key table is missing: {table}")
            actual_count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if actual_count != expected_count:
                raise SystemExit(
                    f"row count mismatch for {table}: expected {expected_count}, got {actual_count}"
                )
finally:
    connection.close()

alembic = ",".join(alembic_revisions) if alembic_revisions else "absent"
status_path.write_text(f"integrity=ok; schema=verified; alembic={alembic}\n", encoding="utf-8")
PY
  publish_restore_dir
  echo "restore drill OK: engine=sqlite; manifest=${MANIFEST_MODE}; sidecar=${SIDECAR_STATUS}; $(cat "${WORK_ROOT}/database-status")"
  echo "restored files: ${RESTORE_DIR}"
  echo "RTO note: record elapsed time and this result in docs/ops/RESTORE_DRILL_LOG.md"
}

postgres_probe() {
  local connection_url_path="$1"
  local mode="$2"
  local manifest_path="$3"
  local status_path="$4"
  "${PYTHON_BIN}" - "${connection_url_path}" "${mode}" "${manifest_path}" "${status_path}" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import psycopg
except ImportError as exc:
    raise SystemExit(
        "PostgreSQL restore requires psycopg; set BOOKER_PYTHON to the Booker venv Python"
    ) from exc

connection_url_path, mode, manifest_name, status_name = sys.argv[1:5]
database_url = Path(connection_url_path).read_text(encoding="utf-8").rstrip("\n")
if not database_url:
    raise SystemExit("password-free PostgreSQL connection URL is empty")
status_path = Path(status_name)

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

with psycopg.connect(database_url) as connection:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_catalog.pg_tables "
            "WHERE schemaname='public' ORDER BY tablename"
        ).fetchall()
    ]
    all_user_tables = connection.execute(
        "SELECT COUNT(*) FROM pg_catalog.pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
    ).fetchone()[0]
    if mode == "empty":
        if all_user_tables != 0:
            raise SystemExit(
                f"PostgreSQL target is not empty ({all_user_tables} user tables); refusing to restore"
            )
        status_path.write_text("empty\n", encoding="utf-8")
        raise SystemExit(0)
    if mode == "legacy":
        if "users" not in tables:
            raise SystemExit("legacy PostgreSQL restore has no users table")
        connection.execute("SELECT COUNT(*) FROM users").fetchone()
        status_path.write_text("legacy-users-readable\n", encoding="utf-8")
        raise SystemExit(0)
    if mode != "v2":
        raise SystemExit(f"unsupported PostgreSQL probe mode: {mode}")

    manifest = json.loads(Path(manifest_name).read_text(encoding="utf-8"))
    metadata = manifest["database"]
    required = metadata.get("required_tables", [])
    if metadata.get("schema_fingerprint_kind") != "postgres_catalog_v2":
        raise SystemExit("unsupported PostgreSQL schema fingerprint")
    if metadata.get("snapshot_consistency") != "pg_export_snapshot":
        raise SystemExit("PostgreSQL manifest lacks a consistent exported snapshot")
    if tables != metadata.get("schema_tables"):
        raise SystemExit("PostgreSQL table set does not match manifest")
    for table in required:
        if not isinstance(table, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise SystemExit(f"invalid required table in manifest: {table!r}")
        if table not in tables:
            raise SystemExit(f"required PostgreSQL table is missing: {table}")

    descriptor = json.loads(
        json.dumps(schema_descriptor(connection), ensure_ascii=False, default=str)
    )
    canonical_schema = json.dumps(
        descriptor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    if descriptor != metadata.get("schema_descriptor"):
        raise SystemExit("PostgreSQL schema catalog does not match manifest")
    if hashlib.sha256(canonical_schema).hexdigest() != metadata.get("schema_sha256"):
        raise SystemExit("PostgreSQL schema SHA-256 does not match manifest")

    revisions = [
        str(row[0])
        for row in connection.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        ).fetchall()
    ]
    if revisions != metadata.get("alembic_revisions") or not revisions:
        raise SystemExit("PostgreSQL Alembic revision does not match manifest")
    for table, expected_count in metadata.get("key_table_counts", {}).items():
        if table not in required:
            raise SystemExit(f"unexpected count table in manifest: {table}")
        actual_count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if actual_count != expected_count:
            raise SystemExit(
                f"row count mismatch for {table}: expected {expected_count}, got {actual_count}"
            )
status_path.write_text("schema=verified; alembic=verified; counts=verified\n", encoding="utf-8")
PY
}

verify_postgres() {
  local dump_format="plain-sql"
  local status_path="${WORK_ROOT}/database-status"

  [[ "${BOOKER_RESTORE_CONFIRM:-}" == "empty-non-production-database" ]] \
    || fail "set BOOKER_RESTORE_CONFIRM=empty-non-production-database after verifying the target is isolated"

  prepare_postgres_connection
  postgres_probe "${POSTGRES_SAFE_URL_FILE}" "empty" "" "${status_path}"

  if command -v pg_restore >/dev/null 2>&1 \
      && pg_restore --list "${EXTRACT_DIR}/booker.dump" >/dev/null 2>&1; then
    dump_format="postgres-custom"
  fi
  if [[ "${MANIFEST_MODE}" == "v2" && "${dump_format}" != "${PAYLOAD_FORMAT}" ]]; then
    fail "PostgreSQL dump format does not match manifest"
  fi

  if [[ "${dump_format}" == "postgres-custom" ]]; then
    require_command pg_restore
    pg_restore --exit-on-error --no-owner --no-privileges \
      --dbname="${POSTGRES_SAFE_URL}" "${EXTRACT_DIR}/booker.dump"
  else
    [[ "${BOOKER_RESTORE_ALLOW_LEGACY_PLAIN_SQL:-}" == "trusted-archive" ]] \
      || fail "legacy plain SQL restore requires BOOKER_RESTORE_ALLOW_LEGACY_PLAIN_SQL=trusted-archive"
    require_command psql
    if grep -Eqi \
        '^[[:space:]]*(CREATE|DROP)[[:space:]]+DATABASE|^[[:space:]]*\\(connect|!)([[:space:]]|$)|COPY[^;]*PROGRAM' \
        "${EXTRACT_DIR}/booker.dump"; then
      fail "legacy plain SQL dump contains database-switching or OS command execution"
    fi
    psql "${POSTGRES_SAFE_URL}" -X -v ON_ERROR_STOP=1 -f "${EXTRACT_DIR}/booker.dump"
  fi

  if [[ "${MANIFEST_MODE}" == "v2" ]]; then
    postgres_probe "${POSTGRES_SAFE_URL_FILE}" "v2" "${EXTRACT_DIR}/manifest.json" "${status_path}"
  else
    postgres_probe "${POSTGRES_SAFE_URL_FILE}" "legacy" "" "${status_path}"
  fi

  publish_restore_dir
  echo "restore drill OK: engine=postgresql; dump=${dump_format}; manifest=${MANIFEST_MODE}; sidecar=${SIDECAR_STATUS}; $(cat "${status_path}")"
  echo "restored files: ${RESTORE_DIR}"
  echo "RTO note: record elapsed time and this result in docs/ops/RESTORE_DRILL_LOG.md"
}

case "${ENGINE}" in
  sqlite)
    RESTORE_DATABASE_URL=""
    [[ "${PAYLOAD}" == "booker.db" ]] || fail "unexpected SQLite payload"
    verify_sqlite
    ;;
  postgresql)
    [[ "${PAYLOAD}" == "booker.dump" ]] || fail "unexpected PostgreSQL payload"
    verify_postgres
    ;;
  *)
    fail "unsupported archive database engine: ${ENGINE}"
    ;;
esac
