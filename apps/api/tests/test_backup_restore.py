import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESTORE_SCRIPT = ROOT / "infra" / "restore-drill.sh"
BACKUP_SCRIPT = ROOT / "infra" / "backup-booker.sh"


def _create_sqlite_database(path: Path, *, complete: bool) -> None:
    tables = ["users"]
    if complete:
        tables.extend(["organizations", "events", "bookings", "payments"])
    with sqlite3.connect(path) as connection:
        for table in tables:
            connection.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY)')
        connection.execute("INSERT INTO users VALUES ('1')")


def _create_legacy_archive(tmp_path: Path, *, payload_name: str, payload: bytes) -> Path:
    stage = tmp_path / f"stage-{payload_name}"
    stage.mkdir()
    (stage / payload_name).write_bytes(payload)
    uploads = stage / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("attachment", encoding="utf-8")
    archive_path = tmp_path / f"legacy-{payload_name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(stage / payload_name, arcname=payload_name)
        archive.add(uploads, arcname="uploads")
    return archive_path


def _create_v2_postgres_archive(tmp_path: Path) -> Path:
    stage = tmp_path / "stage-postgres-v2"
    stage.mkdir()
    dump = stage / "booker.dump"
    dump.write_bytes(b"fake custom-format PostgreSQL fixture")
    uploads = stage / "uploads"
    uploads.mkdir()
    upload = uploads / "sample.txt"
    upload.write_text("attachment", encoding="utf-8")
    manifest = {
        "archive_format": "booker-backup",
        "archive_version": 2,
        "created_at_utc": "2026-09-30T00:00:00Z",
        "database_engine": "postgresql",
        "database_payload": "booker.dump",
        "database_payload_format": "postgres-custom",
        "files_sha256": {
            "booker.dump": hashlib.sha256(dump.read_bytes()).hexdigest(),
            "uploads/sample.txt": hashlib.sha256(upload.read_bytes()).hexdigest(),
        },
        "upload_file_count": 1,
        "upload_total_bytes": upload.stat().st_size,
        # The fake probe validates credential transport; a live staging drill
        # remains responsible for PostgreSQL catalog verification.
        "database": {},
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    archive_path = tmp_path / "postgres-v2.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(manifest_path, arcname="manifest.json")
        archive.add(dump, arcname="booker.dump")
        archive.add(uploads, arcname="uploads")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_name(f"{archive_path.name}.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def _install_fake_postgres_tools(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    assertions = tmp_path / "assert-secure-process.sh"
    _write_executable(
        assertions,
        r'''#!/usr/bin/env bash
set -euo pipefail

assert_no_restore_secret() {
  [[ -z "${BOOKER_RESTORE_DATABASE_URL+x}" ]] || {
    echo "BOOKER_RESTORE_DATABASE_URL leaked into a child environment" >&2
    return 91
  }
  mapfile -t secret_values <"${EXPECTED_SECRET_VALUES_FILE}"
  local secret argument process_part cmdline_path
  for secret in "${secret_values[@]}"; do
    [[ -n "${secret}" ]] || continue
    for argument in "$@"; do
      [[ "${argument}" != *"${secret}"* ]] || {
        echo "restore password leaked into argv" >&2
        return 92
      }
    done
    for cmdline_path in "/proc/$$/cmdline" "/proc/${PPID}/cmdline"; do
      [[ -r "${cmdline_path}" ]] || continue
      while IFS= read -r -d '' process_part; do
        [[ "${process_part}" != *"${secret}"* ]] || {
          echo "restore password leaked into ${cmdline_path}" >&2
          return 93
        }
      done <"${cmdline_path}"
    done
  done
}

assert_private_pgpass() {
  [[ -n "${PGPASSFILE:-}" && -f "${PGPASSFILE}" ]] || {
    echo "temporary PGPASSFILE is unavailable" >&2
    return 94
  }
  [[ "$(stat -c '%a' -- "${PGPASSFILE}")" == "600" ]] || {
    echo "temporary PGPASSFILE mode is not 0600" >&2
    return 95
  }
  [[ -z "${PGPASSWORD+x}" ]] || {
    echo "inherited PGPASSWORD was not removed" >&2
    return 96
  }
  local expected actual
  IFS= read -r expected <"${EXPECTED_PGPASS_FILE}"
  IFS= read -r actual <"${PGPASSFILE}"
  [[ "${actual}" == "${expected}" ]] || {
    echo "temporary PGPASSFILE content is incorrect" >&2
    return 97
  }
  printf '%s\n' "${PGPASSFILE}" >"${SEEN_PGPASS_PATH_FILE}"
}
''',
    )

    fake_python = fake_bin / "python"
    _write_executable(
        fake_python,
        r'''#!/usr/bin/env bash
set -euo pipefail
source "${FAKE_ASSERTIONS_FILE}"
assert_no_restore_secret "$@"
code_file="$(mktemp)"
trap 'rm -f -- "${code_file}"' EXIT
cat >"${code_file}"
{
  printf 'python'
  printf '\t%q' "$@"
  printf '\n'
} >>"${FAKE_CALL_LOG}"
if grep -q 'import psycopg' "${code_file}"; then
  assert_private_pgpass
  [[ "$#" -eq 5 && "$1" == "-" ]] || exit 98
  connection_url="$(cat -- "$2")"
  expected_safe_url="$(cat -- "${EXPECTED_SAFE_URL_FILE}")"
  [[ "${connection_url}" == "${expected_safe_url}" ]] || {
    echo "Python probe received an unexpected connection URL" >&2
    exit 99
  }
  printf '%s-ok\n' "$3" >"$5"
  exit 0
fi
"${REAL_PYTHON}" "$@" <"${code_file}"
''',
    )

    fake_pg_restore = fake_bin / "pg_restore"
    _write_executable(
        fake_pg_restore,
        r'''#!/usr/bin/env bash
set -euo pipefail
source "${FAKE_ASSERTIONS_FILE}"
assert_no_restore_secret "$@"
{
  printf 'pg_restore'
  printf '\t%q' "$@"
  printf '\n'
} >>"${FAKE_CALL_LOG}"
if [[ "${1:-}" == "--list" ]]; then
  [[ "${FAKE_DUMP_FORMAT}" == "custom" ]]
  exit
fi
assert_private_pgpass
expected_safe_url="$(cat -- "${EXPECTED_SAFE_URL_FILE}")"
found=0
for argument in "$@"; do
  [[ "${argument}" == "--dbname=${expected_safe_url}" ]] && found=1
done
[[ "${found}" == "1" ]] || {
  echo "pg_restore did not receive the password-free URL" >&2
  exit 100
}
''',
    )

    fake_psql = fake_bin / "psql"
    _write_executable(
        fake_psql,
        r'''#!/usr/bin/env bash
set -euo pipefail
source "${FAKE_ASSERTIONS_FILE}"
assert_no_restore_secret "$@"
assert_private_pgpass
{
  printf 'psql'
  printf '\t%q' "$@"
  printf '\n'
} >>"${FAKE_CALL_LOG}"
expected_safe_url="$(cat -- "${EXPECTED_SAFE_URL_FILE}")"
[[ "${1:-}" == "${expected_safe_url}" ]] || {
  echo "psql did not receive the password-free URL" >&2
  exit 101
}
''',
    )
    return fake_bin, fake_python, assertions, tmp_path / "fake-calls.log"


def test_restore_drill_script_smoke_with_uploads(tmp_path: Path):
    assert RESTORE_SCRIPT.is_file()
    staging = tmp_path / "stage"
    staging.mkdir()
    db = staging / "booker.db"
    _create_sqlite_database(db, complete=False)
    uploads = staging / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("attachment", encoding="utf-8")
    backup = tmp_path / "booker-backup.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(db, arcname="booker.db")
        archive.add(uploads, arcname="uploads")
    restore_dir = tmp_path / "restore"
    out = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), str(backup), str(restore_dir)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert "restore drill OK" in out.stdout
    assert (restore_dir / "uploads" / "sample.txt").is_file()


def test_pg_dump_url_strips_psycopg_driver():
    text = BACKUP_SCRIPT.read_text(encoding="utf-8")
    assert "postgresql+psycopg/postgresql" in text
    assert 'pg_dump "$(pg_url_for_libpq' in text


def test_backup_includes_upload_dir(tmp_path: Path):
    db_path = tmp_path / "booker.db"
    _create_sqlite_database(db_path, complete=True)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "file.bin").write_bytes(b"payload")
    backup_root = tmp_path / "backups"
    env = {
        **os.environ,
        "BOOKER_PYTHON": sys.executable,
        "BOOKER_DATABASE_URL": f"sqlite:///{db_path}",
        "BOOKER_UPLOAD_DIR": str(upload_dir),
        "BOOKER_BACKUP_DIR": str(backup_root),
    }
    subprocess.run(["bash", str(BACKUP_SCRIPT)], check=True, env=env)
    archives = list(backup_root.glob("booker-*.tar.gz"))
    assert archives
    with tarfile.open(archives[0], "r:gz") as archive:
        names = archive.getnames()
    assert "booker.db" in names
    assert any(name.startswith("uploads/") for name in names)


def test_v2_sqlite_backup_round_trip(tmp_path: Path):
    db_path = tmp_path / "booker.db"
    _create_sqlite_database(db_path, complete=True)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "fixture.txt").write_text("v2", encoding="utf-8")
    backup_root = tmp_path / "backups"
    env = {
        **os.environ,
        "BOOKER_PYTHON": sys.executable,
        "BOOKER_DATABASE_URL": f"sqlite:///{db_path}",
        "BOOKER_UPLOAD_DIR": str(upload_dir),
        "BOOKER_BACKUP_DIR": str(backup_root),
    }
    subprocess.run(["bash", str(BACKUP_SCRIPT)], check=True, env=env)
    backup = next(backup_root.glob("booker-*.tar.gz"))
    restore_dir = tmp_path / "restore-v2"
    result = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), str(backup), str(restore_dir)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert "engine=sqlite; manifest=v2; sidecar=verified" in result.stdout
    assert (restore_dir / "manifest.json").is_file()
    assert (restore_dir / "uploads" / "fixture.txt").read_text(encoding="utf-8") == "v2"


@pytest.mark.parametrize(
    ("fixture_kind", "dump_format", "expected_command", "password_location"),
    [
        ("v2-custom", "custom", "pg_restore", "authority"),
        ("legacy-plain", "plain", "psql", "query"),
    ],
)
def test_postgres_restore_password_never_reaches_argv_or_proc_cmdline(
    tmp_path: Path,
    fixture_kind: str,
    dump_format: str,
    expected_command: str,
    password_location: str,
):
    if fixture_kind == "v2-custom":
        backup = _create_v2_postgres_archive(tmp_path)
    else:
        backup = _create_legacy_archive(
            tmp_path,
            payload_name="booker.dump",
            payload=b"CREATE TABLE users (id text);\n",
        )

    fake_bin, fake_python, assertions, call_log = _install_fake_postgres_tools(tmp_path)
    encoded_password = "s3cr%3Aet%5Cvalue"
    decoded_password = r"s3cr:et\value"
    safe_url = "postgresql://restore_user@db.example:5544/booker_restore?sslmode=require"
    if password_location == "authority":
        restore_url = (
            f"postgresql+psycopg://restore_user:{encoded_password}"
            "@db.example:5544/booker_restore?sslmode=require"
        )
    else:
        restore_url = (
            "postgresql+psycopg://restore_user@db.example:5544/booker_restore"
            f"?sslmode=require&password={encoded_password}"
        )
    expected_pgpass = r"db.example:5544:booker_restore:restore_user:s3cr\:et\\value"

    expected_secrets_file = tmp_path / "expected-secrets"
    expected_secrets_file.write_text(
        f"{encoded_password}\n{decoded_password}\n", encoding="utf-8"
    )
    expected_safe_url_file = tmp_path / "expected-safe-url"
    expected_safe_url_file.write_text(f"{safe_url}\n", encoding="utf-8")
    expected_pgpass_file = tmp_path / "expected-pgpass"
    expected_pgpass_file.write_text(f"{expected_pgpass}\n", encoding="utf-8")
    seen_pgpass_path_file = tmp_path / "seen-pgpass-path"

    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "BOOKER_PYTHON": str(fake_python),
        "BOOKER_RESTORE_DATABASE_URL": restore_url,
        "BOOKER_RESTORE_CONFIRM": "empty-non-production-database",
        "BOOKER_RESTORE_ALLOW_LEGACY_PLAIN_SQL": "trusted-archive",
        "PGPASSWORD": "must-be-removed",
        "REAL_PYTHON": sys.executable,
        "FAKE_ASSERTIONS_FILE": str(assertions),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_DUMP_FORMAT": dump_format,
        "EXPECTED_SECRET_VALUES_FILE": str(expected_secrets_file),
        "EXPECTED_SAFE_URL_FILE": str(expected_safe_url_file),
        "EXPECTED_PGPASS_FILE": str(expected_pgpass_file),
        "SEEN_PGPASS_PATH_FILE": str(seen_pgpass_path_file),
    }
    restore_dir = tmp_path / f"restore-{fixture_kind}"
    result = subprocess.run(
        ["bash", "-x", str(RESTORE_SCRIPT), str(backup), str(restore_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "restore drill OK: engine=postgresql" in result.stdout
    calls = call_log.read_text(encoding="utf-8")
    assert expected_command in calls
    assert encoded_password not in calls
    assert decoded_password not in calls
    assert encoded_password not in result.stderr
    assert decoded_password not in result.stderr
    pgpass_path = Path(seen_pgpass_path_file.read_text(encoding="utf-8").strip())
    assert not pgpass_path.exists(), "cleanup must remove the temporary PGPASSFILE"
    assert (restore_dir / "booker.dump").is_file()
