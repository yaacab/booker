import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


def _write_manifest(root: Path, staging: Path) -> None:
    subprocess.run(
        [sys.executable, str(root / "infra" / "backup_support.py"), "manifest", str(staging)],
        check=True,
    )


def test_restore_drill_script_smoke_with_uploads():
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "restore-drill.sh"
    assert script.is_file()
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "stage"
        staging.mkdir()
        db = staging / "booker.db"
        uploads = staging / "uploads"
        uploads.mkdir()
        (uploads / "sample.txt").write_text("attachment", encoding="utf-8")
        with sqlite3.connect(db) as connection:
            connection.executescript("CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('1');")
        _write_manifest(root, staging)
        backup = Path(tmp) / "booker-backup.tar.gz"
        with tarfile.open(backup, "w:gz") as archive:
            archive.add(db, arcname="booker.db")
            archive.add(uploads, arcname="uploads")
            archive.add(staging / "backup-manifest.json", arcname="backup-manifest.json")
        restore = Path(tmp) / "restore"
        out = subprocess.run(
            ["bash", str(script), str(backup), str(restore)],
            capture_output=True,
            text=True,
            check=True,
            env={**dict(__import__("os").environ), "BOOKER_PYTHON": sys.executable},
        )
        assert "restore drill OK" in out.stdout
        assert (restore / "uploads" / "sample.txt").is_file()
        stale = subprocess.run(
            ["bash", str(script), str(backup), str(restore)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "BOOKER_PYTHON": sys.executable},
        )
        assert stale.returncode != 0
        assert "must not exist" in stale.stderr


def test_restore_rejects_incomplete_archive_and_non_tmp_target(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "restore-drill.sh"
    incomplete = tmp_path / "incomplete.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("not a database", encoding="utf-8")
    with tarfile.open(incomplete, "w:gz") as archive:
        archive.add(payload, arcname="payload.txt")
    target = tmp_path / "restore"
    failed = subprocess.run(
        ["bash", str(script), str(incomplete), str(target)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert failed.returncode != 0
    assert not target.exists()
    non_tmp = subprocess.run(
        ["bash", str(script), str(incomplete), "/opt/booker/restore-must-not-run"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert non_tmp.returncode != 0
    assert "must resolve under /tmp" in non_tmp.stderr

    traversal = subprocess.run(
        ["bash", str(script), str(incomplete), "/tmp/../opt/booker/data"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert traversal.returncode != 0
    assert "must resolve under /tmp" in traversal.stderr


def test_postgres_backup_uses_custom_dump_and_strips_driver(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "run-booker-backup.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "pg-dump-args.txt"
    service_copy = tmp_path / "pg-service-copy.txt"
    fake_pg_dump = fake_bin / "pg_dump"
    fake_pg_dump.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "${BOOKER_TEST_PG_ARGS}"
cp "${PGSERVICEFILE}" "${BOOKER_TEST_PG_SERVICE}"
for arg in "$@"; do
  case "$arg" in
    --file=*) printf 'custom-dump' > "${arg#--file=}" ;;
  esac
done
""",
        encoding="utf-8",
    )
    fake_pg_dump.chmod(0o755)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "proof.txt").write_text("upload", encoding="utf-8")
    backup_root = tmp_path / "backups"
    env_file = tmp_path / "booker-api.env"
    env_file.write_text(
        "BOOKER_DATABASE_URL=postgresql+psycopg://booker:secret@db/booker\n",
        encoding="utf-8",
    )
    env = {
        **dict(__import__("os").environ),
        "PATH": f"{fake_bin}:{__import__('os').environ['PATH']}",
        "BOOKER_TEST_PG_ARGS": str(args_file),
        "BOOKER_TEST_PG_SERVICE": str(service_copy),
        "BOOKER_ENV_FILE": str(env_file),
        "BOOKER_UPLOAD_DIR": str(uploads),
        "BOOKER_BACKUP_DIR": str(backup_root),
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(["bash", str(script)], check=True, env=env)
    args = args_file.read_text(encoding="utf-8").splitlines()
    assert args[0] == "--format=custom"
    assert args[1].startswith("--file=")
    assert args[2] == "service=booker_backup"
    assert "secret" not in " ".join(args)
    service = service_copy.read_text(encoding="utf-8")
    assert "host=db" in service
    assert "user=booker" in service
    assert "password=secret" in service
    archive = next(backup_root.glob("booker-pg-*.tar.gz"))
    with tarfile.open(archive, "r:gz") as bundle:
        names = bundle.getnames()
        assert bundle.extractfile("booker.dump").read() == b"custom-dump"
    assert "uploads/proof.txt" in names
    assert "backup-manifest.json" in names
    assert archive.stat().st_mode & 0o777 == 0o600


def test_backup_includes_upload_dir(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "backup-booker.sh"
    db_path = tmp_path / "booker.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "file.bin").write_bytes(b"payload")
    backup_root = tmp_path / "backups"
    with sqlite3.connect(db_path) as connection:
        connection.executescript("CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('1');")
    env = {
        **dict(__import__("os").environ),
        "BOOKER_DATABASE_URL": f"sqlite:///{db_path}",
        "BOOKER_UPLOAD_DIR": str(upload_dir),
        "BOOKER_BACKUP_DIR": str(backup_root),
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(["bash", str(script)], check=True, env=env)
    archives = list(backup_root.glob("booker-*.tar.gz"))
    assert archives
    with tarfile.open(archives[0], "r:gz") as archive:
        names = archive.getnames()
        manifest = json.load(archive.extractfile("backup-manifest.json"))
    assert "booker.db" in names
    assert any(name.startswith("uploads/") for name in names)
    assert {entry["path"] for entry in manifest["files"]} == {"booker.db", "uploads/file.bin"}
    assert archives[0].stat().st_mode & 0o777 == 0o600
    assert backup_root.stat().st_mode & 0o777 == 0o700


def test_backup_rejects_missing_sqlite_and_upload_directory(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "backup-booker.sh"
    backup_root = tmp_path / "backups"
    missing_db = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "BOOKER_DATABASE_URL": f"sqlite:///{tmp_path / 'missing.db'}",
            "BOOKER_UPLOAD_DIR": str(tmp_path / "missing-uploads"),
            "BOOKER_BACKUP_DIR": str(backup_root),
            "BOOKER_PYTHON": sys.executable,
        },
    )
    assert missing_db.returncode != 0
    assert not list(backup_root.glob("booker-*.tar.gz"))

    db_path = tmp_path / "booker.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
    missing_uploads = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "BOOKER_DATABASE_URL": f"sqlite:///{db_path}",
            "BOOKER_UPLOAD_DIR": str(tmp_path / "missing-uploads"),
            "BOOKER_BACKUP_DIR": str(backup_root),
            "BOOKER_PYTHON": sys.executable,
        },
    )
    assert missing_uploads.returncode != 0
    assert not list(backup_root.glob("booker-*.tar.gz"))


def test_restore_failure_after_extract_removes_partial_target(tmp_path):
    root = Path(__file__).resolve().parents[3]
    staging = tmp_path / "stage"
    staging.mkdir()
    db = staging / "booker.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE support_tickets (id TEXT)")
    (staging / "uploads").mkdir()
    _write_manifest(root, staging)
    backup = tmp_path / "booker-invalid.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        for name in ("booker.db", "uploads", "backup-manifest.json"):
            archive.add(staging / name, arcname=name)
    target = tmp_path / "restore"
    result = subprocess.run(
        ["bash", str(root / "infra" / "restore-drill.sh"), str(backup), str(target)],
        capture_output=True, text=True, check=False,
        env={**os.environ, "BOOKER_PYTHON": sys.executable},
    )
    assert result.returncode != 0
    assert not target.exists()


def test_backup_same_second_keeps_both_archives_and_failed_tar_cleans_partial(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "backup-booker.sh"
    db = tmp_path / "booker.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    backup_root = tmp_path / "backups"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_date = fake_bin / "date"
    fake_date.write_text("#!/bin/sh\necho 20261001T120000Z\n", encoding="utf-8")
    fake_date.chmod(0o755)
    env = {
        **os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BOOKER_DATABASE_URL": f"sqlite:///{db}",
        "BOOKER_UPLOAD_DIR": str(uploads), "BOOKER_BACKUP_DIR": str(backup_root),
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    assert len(list(backup_root.glob("booker-*.tar.gz"))) == 2

    fake_tar = fake_bin / "tar"
    fake_tar.write_text(
        "#!/bin/sh\nprintf 'partial' > \"$2\"\nexit 7\n", encoding="utf-8"
    )
    fake_tar.chmod(0o755)
    failed = subprocess.run(
        ["bash", str(script)], env=env, check=False, capture_output=True, text=True
    )
    assert failed.returncode != 0
    assert not list(backup_root.glob("*.partial"))
    assert not list(backup_root.glob(".staging-*"))
    assert len(list(backup_root.glob("booker-*.tar.gz"))) == 2


def test_backup_retention_dry_run_keeps_existing_archive(tmp_path):
    root = Path(__file__).resolve().parents[3]
    db = tmp_path / "booker.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    old = backup_root / "booker-old.tar.gz"
    old.write_bytes(b"old archive sentinel")
    old_time = time.time() - 40 * 86400
    os.utime(old, (old_time, old_time))
    env = {
        **os.environ, "BOOKER_DATABASE_URL": f"sqlite:///{db}",
        "BOOKER_UPLOAD_DIR": str(uploads), "BOOKER_BACKUP_DIR": str(backup_root),
        "BOOKER_BACKUP_RETENTION_DAYS": "30", "BOOKER_BACKUP_RETENTION_DRY_RUN": "1",
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(["bash", str(root / "infra" / "backup-booker.sh")], env=env, check=True)
    assert old.read_bytes() == b"old archive sentinel"
    subprocess.run(
        ["bash", str(root / "infra" / "backup-booker.sh")],
        env={**env, "BOOKER_BACKUP_RETENTION_DRY_RUN": "0"}, check=True,
    )
    assert not old.exists()
    assert len(list(backup_root.glob("booker-*.tar.gz"))) >= 1
    rejected = subprocess.run(
        ["bash", str(root / "infra" / "backup-booker.sh")],
        env={**env, "BOOKER_BACKUP_RETENTION_DAYS": "-1"},
        check=False, capture_output=True,
    )
    assert rejected.returncode != 0


def test_backup_wrapper_keeps_online_api_running_by_default(tmp_path):
    root = Path(__file__).resolve().parents[3]
    db = tmp_path / "booker.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    actions = tmp_path / "systemctl-actions"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/bin/sh\necho \"$*\" >> \"$BOOKER_TEST_SYSTEMCTL_ACTIONS\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)
    env = {
        **os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BOOKER_TEST_SYSTEMCTL_ACTIONS": str(actions),
        "BOOKER_DATABASE_URL": f"sqlite:///{db}",
        "BOOKER_UPLOAD_DIR": str(uploads),
        "BOOKER_BACKUP_DIR": str(tmp_path / "backups"),
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(
        ["bash", str(root / "infra" / "run-booker-backup.sh")],
        env=env, check=True, capture_output=True,
    )
    assert not actions.exists()


def test_backup_wrapper_attempts_restart_when_opt_in_stop_fails(tmp_path):
    root = Path(__file__).resolve().parents[3]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    actions = tmp_path / "systemctl-actions"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/bin/sh\necho \"$*\" >> \"$BOOKER_TEST_SYSTEMCTL_ACTIONS\"\n"
        "if [ \"$1\" = stop ]; then exit 1; fi\nexit 0\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "infra" / "run-booker-backup.sh")],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BOOKER_TEST_SYSTEMCTL_ACTIONS": str(actions),
            "BOOKER_BACKUP_QUIESCE_SERVICE": "booker-test-only",
            "BOOKER_DATABASE_URL": f"sqlite:///{tmp_path / 'unused.db'}",
            "BOOKER_PYTHON": sys.executable,
        },
        check=False, capture_output=True,
    )
    assert result.returncode != 0
    assert actions.read_text().splitlines() == [
        "is-active --quiet booker-test-only",
        "stop booker-test-only",
        "start booker-test-only",
    ]


def test_local_backup_restore_representative_metadata_and_tamper(tmp_path):
    root = Path(__file__).resolve().parents[3]
    db = tmp_path / "pilot.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);"
            "CREATE TABLE organizations (id TEXT PRIMARY KEY, name TEXT);"
            "CREATE TABLE support_tickets (id TEXT PRIMARY KEY, author_user_id TEXT, status TEXT);"
            "CREATE TABLE payments (id TEXT PRIMARY KEY, amount_rub INTEGER, status TEXT);"
            "INSERT INTO users VALUES ('user-1','synthetic@example.invalid');"
            "INSERT INTO organizations VALUES ('org-1','Synthetic tenant');"
            "INSERT INTO support_tickets VALUES ('ticket-1','user-1','open');"
            "INSERT INTO payments VALUES ('payment-1',1234,'external_recorded');"
        )
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("synthetic upload", encoding="utf-8")
    backup_root = tmp_path / "backups"
    env = {
        **os.environ, "BOOKER_DATABASE_URL": f"sqlite:///{db}",
        "BOOKER_UPLOAD_DIR": str(uploads), "BOOKER_BACKUP_DIR": str(backup_root),
        "BOOKER_PYTHON": sys.executable,
    }
    subprocess.run(
        ["bash", str(root / "infra" / "backup-booker.sh")], env=env, check=True,
        capture_output=True,
    )
    archive_path = next(backup_root.glob("booker-*.tar.gz"))
    assert archive_path.stat().st_mode & 0o777 == 0o600
    assert backup_root.stat().st_mode & 0o777 == 0o700
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest = json.load(archive.extractfile("backup-manifest.json"))
        stored_db = archive.extractfile("booker.db").read()
        db_entry = next(row for row in manifest["files"] if row["path"] == "booker.db")
        assert db_entry["sha256"] == hashlib.sha256(stored_db).hexdigest()
        assert {row["path"] for row in manifest["files"]} == {
            "booker.db", "uploads/sample.txt",
        }
    restore = tmp_path / "restore"
    subprocess.run(
        ["bash", str(root / "infra" / "restore-drill.sh"), str(archive_path), str(restore)],
        env=env, check=True, capture_output=True,
    )
    assert restore.stat().st_mode & 0o777 == 0o700
    with sqlite3.connect(restore / "booker.db") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT name FROM organizations").fetchone()[0] == "Synthetic tenant"
        assert connection.execute("SELECT status FROM support_tickets").fetchone()[0] == "open"
        assert connection.execute("SELECT amount_rub FROM payments").fetchone()[0] == 1234
    assert (restore / "uploads" / "sample.txt").read_text() == "synthetic upload"

    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive_path, "r:gz") as source, tarfile.open(tampered, "w:gz") as target:
        for member in source.getmembers():
            if member.name == "uploads/sample.txt":
                payload = b"tampered upload"
                member.size = len(payload)
                target.addfile(member, io.BytesIO(payload))
            elif member.isfile():
                target.addfile(member, source.extractfile(member))
            else:
                target.addfile(member)
    bad_target = tmp_path / "tampered-restore"
    rejected = subprocess.run(
        ["bash", str(root / "infra" / "restore-drill.sh"), str(tampered), str(bad_target)],
        env=env, check=False, capture_output=True,
    )
    assert rejected.returncode != 0
    assert not bad_target.exists()

    extra_archive = tmp_path / "extra.tar.gz"
    with tarfile.open(archive_path, "r:gz") as source, tarfile.open(extra_archive, "w:gz") as target:
        for member in source.getmembers():
            target.addfile(member, source.extractfile(member) if member.isfile() else None)
        payload = b"unlisted"
        extra = tarfile.TarInfo("uploads/unlisted.txt")
        extra.size = len(payload)
        target.addfile(extra, io.BytesIO(payload))
    extra_target = tmp_path / "extra-restore"
    rejected_extra = subprocess.run(
        ["bash", str(root / "infra" / "restore-drill.sh"), str(extra_archive), str(extra_target)],
        env=env, check=False, capture_output=True,
    )
    assert rejected_extra.returncode != 0
    assert not extra_target.exists()
