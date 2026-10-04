"""Synthetic v2 backup identity and restore evidence; no production resources."""

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from booker_api.ops_monitor import evidence_snapshot, snapshot_signals

ROOT = Path(__file__).resolve().parents[3]


def _contract():
    spec = importlib.util.spec_from_file_location("booker_backup_contract", ROOT / "infra" / "backup_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp_path, *, sealed=False):
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('sample');"
            "CREATE TABLE alembic_version (version_num TEXT);"
            "INSERT INTO alembic_version VALUES ('local-revision');"
        )
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("synthetic attachment", encoding="utf-8")
    env = {
        **os.environ,
        "BOOKER_DATABASE_URL": f"sqlite:///{database}",
        "BOOKER_UPLOAD_DIR": str(uploads),
        "BOOKER_BACKUP_DIR": str(tmp_path / "backups"),
        "BOOKER_RUNTIME_ENV": "test",
        "BOOKER_BACKUP_FORMAT": "sealed" if sealed else "legacy",
        "BOOKER_PYTHON": sys.executable,
    }
    if sealed:
        key = tmp_path / "key"
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        env["BOOKER_BACKUP_KEY_FILE"] = str(key)
        env["BOOKER_BACKUP_CRYPTO_PYTHON"] = shutil.which("python3") or sys.executable
    return env


def _backup(env):
    result = subprocess.run(
        [str(ROOT / "infra" / "run-booker-ops-backup.sh")],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    archive = next(backup_dir.glob("booker-*.bke" if env["BOOKER_BACKUP_FORMAT"] == "sealed" else "booker-*.tar.gz"))
    marker = json.loads((backup_dir / ".ops-backup.json").read_text())
    return archive, marker


def _restore(env, archive, target):
    return subprocess.run(
        [str(ROOT / "infra" / "run-booker-ops-restore-drill.sh"), str(archive), str(target)],
        env=env, capture_output=True, text=True, check=False,
    )


def test_v2_exact_archive_and_restored_attachment_binding(tmp_path):
    env = _env(tmp_path)
    archive, marker = _backup(env)
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    assert marker["version"] == 2 and marker["status"] == "ok"
    assert marker["db_engine"] == "sqlite"
    assert marker["schema_revision"] == "local-revision"
    assert marker["source_environment"] == "test"
    assert marker["attachments"]["count"] == 1
    assert marker["attachments"]["bytes"] == len("synthetic attachment")
    assert marker["archive_bytes"] == archive.stat().st_size
    assert len(marker["archive_sha256"]) == 64
    assert "sqlite:///" not in json.dumps(marker)
    assert (backup_dir / ".ops-backup.json").stat().st_mode & 0o777 == 0o600
    assert not list(backup_dir.glob("*.partial"))
    assert not list(backup_dir.glob(".booker-evidence-*"))

    before = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    assert before["backup_not_restored"] == 1
    target = tmp_path / "restored"
    restored = _restore(env, archive, target)
    assert restored.returncode == 0, restored.stderr
    assert (target / "uploads" / "sample.txt").read_text() == "synthetic attachment"
    restore_marker = json.loads((backup_dir / ".ops-restore.json").read_text())
    assert restore_marker["archive_id"] == marker["archive_id"]
    assert restore_marker["archive_sha256"] == marker["archive_sha256"]
    assert restore_marker["attachments"] == marker["attachments"]
    assert restore_marker["verifier_version"] == "booker-restore-v2"
    after = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    assert after["backup_not_restored"] == 0
    assert not {"restore_mismatch", "db_engine_mismatch"} & {s.key for s in snapshot_signals(after)}


def test_tamper_wrong_archive_and_engine_fail_closed(tmp_path):
    env = _env(tmp_path)
    archive, marker = _backup(env)
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    wrong = backup_dir / "booker-wrong.tar.gz"
    shutil.copy2(archive, wrong)
    target = tmp_path / "wrong-target"
    assert _restore(env, wrong, target).returncode != 0
    assert not target.exists()
    assert _restore({**env, "BOOKER_DATABASE_URL": "postgresql://unused/test"}, archive,
                    tmp_path / "engine-target").returncode != 0
    assert not (tmp_path / "engine-target").exists()
    changed = bytearray(archive.read_bytes())
    changed[-1] ^= 1
    archive.write_bytes(changed)
    assert _restore(env, archive, tmp_path / "tampered-target").returncode != 0
    assert not (tmp_path / "tampered-target").exists()
    snapshot = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    assert snapshot["backup_binding"] == "mismatch"
    assert "backup_archive_mismatch" in {s.key for s in snapshot_signals(snapshot)}
    assert marker["archive_id"]


def test_previous_archive_can_be_drilled_but_latest_stays_unrestored(tmp_path):
    env = _env(tmp_path)
    first, first_marker = _backup(env)
    result = subprocess.run(
        [str(ROOT / "infra" / "run-booker-ops-backup.sh")], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    latest = json.loads((backup_dir / ".ops-backup.json").read_text())
    assert latest["archive_id"] != first_marker["archive_id"]
    assert first.is_file() and first.with_name(first.name + ".evidence.json").is_file()
    assert _restore(env, first, tmp_path / "older-restore").returncode == 0
    snapshot = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    assert snapshot["restore_mismatch"] == 1
    assert snapshot["backup_not_restored"] == 1


def test_orphan_new_archive_and_engine_mismatch_are_visible(tmp_path, monkeypatch):
    env = _env(tmp_path)
    archive, _ = _backup(env)
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    orphan = backup_dir / "booker-orphan.tar.gz"
    shutil.copy2(archive, orphan)
    new_time = archive.stat().st_mtime + 60
    os.utime(orphan, (new_time, new_time))
    monkeypatch.setattr("booker_api.ops_monitor.settings.database_url", "postgresql://unused/test")
    snapshot = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    keys = {signal.key for signal in snapshot_signals(snapshot)}
    assert {"backup_unbound_archive", "db_engine_mismatch"} <= keys


def test_restored_database_revision_must_match_evidence(tmp_path):
    env = _env(tmp_path)
    archive, _ = _backup(env)
    target = tmp_path / "verified-restore"
    assert _restore(env, archive, target).returncode == 0
    with sqlite3.connect(target / "booker.db") as db:
        db.execute("UPDATE alembic_version SET version_num='changed'")
    contract = _contract()
    with pytest.raises(ValueError, match="schema revision mismatch"):
        contract.record_restore(
            tmp_path / "should-not-exist.json", archive.with_name(archive.name + ".evidence.json"),
            archive, target, "2026-10-02T00:00:00+00:00",
        )
    assert not (tmp_path / "should-not-exist.json").exists()


def test_legacy_marker_is_unknown_and_restore_not_green(tmp_path):
    env = _env(tmp_path)
    archive, _ = _backup(env)
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    archive.with_name(archive.name + ".evidence.json").unlink()
    (backup_dir / ".ops-backup.json").write_text(json.dumps({
        "version": 1, "kind": "backup", "status": "ok", "at": "2026-10-02T00:00:00+00:00",
    }))
    target = tmp_path / "legacy-target"
    assert _restore(env, archive, target).returncode == 0
    assert json.loads((backup_dir / ".ops-restore.json").read_text())["status"] == "unknown"
    snapshot = evidence_snapshot(backup_dir, datetime.now(timezone.utc))
    keys = {s.key for s in snapshot_signals(snapshot)}
    assert "backup_evidence_legacy" in keys
    assert "restore_evidence_legacy" in keys


def test_atomic_evidence_preserves_previous_marker_on_replace_failure(tmp_path, monkeypatch):
    contract = _contract()
    path = tmp_path / "marker.json"
    contract.record_failure(path, "backup", "2026-10-02T00:00:00+00:00")
    original = path.read_bytes()
    monkeypatch.setattr(contract.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        contract.record_failure(path, "backup", "2026-10-02T00:01:00+00:00")
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".booker-evidence-*"))


def test_archive_publication_failure_does_not_create_visible_archive(tmp_path, monkeypatch):
    contract = _contract()
    partial = tmp_path / "booker-example.tar.gz.partial"
    partial.write_bytes(b"synthetic")
    destination = tmp_path / "booker-example.tar.gz"
    monkeypatch.setattr(contract.os, "link", lambda *_args: (_ for _ in ()).throw(OSError("link failed")))
    with pytest.raises(OSError, match="link failed"):
        contract.publish(partial, destination)
    assert not destination.exists()
    assert partial.is_file()


def test_sealed_v2_wrong_key_cannot_write_restore_success(tmp_path):
    runtime = shutil.which("python3") or sys.executable
    if subprocess.run([runtime, "-c", "import cryptography"], check=False, capture_output=True).returncode:
        pytest.skip("opt-in cryptography runtime unavailable")
    env = _env(tmp_path, sealed=True)
    archive, marker = _backup(env)
    assert marker["encryption"] == "sealed-aes-256-gcm-v1"
    wrong_key = tmp_path / "wrong-key"
    wrong_key.write_bytes(os.urandom(32))
    wrong_key.chmod(0o600)
    bad = _restore({**env, "BOOKER_BACKUP_KEY_FILE": str(wrong_key)}, archive,
                   tmp_path / "wrong-key-target")
    assert bad.returncode != 0
    assert not (tmp_path / "wrong-key-target").exists()
    evidence = json.loads((Path(env["BOOKER_BACKUP_DIR"]) / ".ops-restore.json").read_text())
    assert evidence["status"] == "failed"
    assert _restore(env, archive, tmp_path / "sealed-target").returncode == 0


def test_postgres_contract_never_uses_sqlite_restore_drill(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "booker.dump").write_bytes(b"synthetic pg_dump placeholder")
    (staging / "uploads").mkdir()
    subprocess.run(
        [sys.executable, str(ROOT / "infra" / "backup_support.py"), "manifest", str(staging)],
        check=True, capture_output=True,
    )
    manifest = json.loads((staging / "backup-manifest.json").read_text())
    assert manifest["db_engine"] == "postgresql"
    assert manifest["schema_revision"] == "unknown"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    archive = backup_dir / "booker-pg-synthetic.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for name in ("booker.dump", "uploads", "backup-manifest.json"):
            output.add(staging / name, arcname=name)
    subprocess.run(
        [sys.executable, str(ROOT / "infra" / "backup_support.py"), "verify-archive", str(archive)],
        check=True, capture_output=True,
    )
    contract = _contract()
    contract.record_backup(backup_dir / ".ops-backup.json", archive, staging / "backup-manifest.json")
    result = _restore({
        **os.environ, "BOOKER_BACKUP_DIR": str(backup_dir),
        "BOOKER_DATABASE_URL": "postgresql://unused/test",
    }, archive, tmp_path / "pg-target")
    assert result.returncode != 0
    assert not (tmp_path / "pg-target").exists()
    restore = json.loads((backup_dir / ".ops-restore.json").read_text())
    assert restore["status"] == "unknown"
    assert restore["reason"] == "postgresql_restore_unverified"


def test_postgres_contract_harness_is_opt_in():
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: PostgreSQL restore not verified")
    from sqlalchemy import text

    from tests.postgres_harness import isolated_postgres_schema

    with isolated_postgres_schema(dsn) as (engine, _config, schema), engine.connect() as connection:
        assert connection.execute(text("SELECT current_schema()")).scalar_one() == schema
