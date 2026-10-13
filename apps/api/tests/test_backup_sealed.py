"""Synthetic sealed backup/restore drills; no production data or key material."""

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CRYPTO_PY = shutil.which("python3")


@pytest.fixture(autouse=True)
def require_crypto_python():
    if not CRYPTO_PY:
        pytest.skip("python3 unavailable")
    available = subprocess.run(
        [CRYPTO_PY, "-c", "import cryptography"], capture_output=True, check=False
    )
    if available.returncode:
        pytest.skip("opt-in cryptography runtime unavailable")


def _key(path: Path) -> Path:
    path.write_bytes(os.urandom(32))
    path.chmod(0o600)
    return path


def _environment(tmp_path: Path, key: Path) -> dict[str, str]:
    database = tmp_path / "booker.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('SEALED_DB_MARKER');"
        )
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("SEALED_UPLOAD_MARKER", encoding="utf-8")
    return {
        **os.environ,
        "BOOKER_DATABASE_URL": f"sqlite:///{database}",
        "BOOKER_UPLOAD_DIR": str(uploads),
        "BOOKER_BACKUP_DIR": str(tmp_path / "backups"),
        "BOOKER_BACKUP_FORMAT": "sealed",
        "BOOKER_BACKUP_KEY_FILE": str(key),
        "BOOKER_BACKUP_CRYPTO_PYTHON": CRYPTO_PY,
        "BOOKER_PYTHON": sys.executable,
    }


def _backup(env: dict[str, str]) -> Path:
    backup_dir = Path(env["BOOKER_BACKUP_DIR"])
    before = set(backup_dir.glob("booker-*.bke")) if backup_dir.exists() else set()
    subprocess.run(["bash", str(ROOT / "infra" / "backup-booker.sh")], env=env, check=True)
    created = set(backup_dir.glob("booker-*.bke")) - before
    assert len(created) == 1
    return created.pop()


def _restore(archive: Path, target: Path, env: dict[str, str]):
    return subprocess.run(
        ["bash", str(ROOT / "infra" / "restore-drill.sh"), str(archive), str(target)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sealed_round_trip_permissions_and_rotation(tmp_path):
    key1 = _key(tmp_path / "key-1")
    env = _environment(tmp_path, key1)
    first = _backup(env)
    assert first.stat().st_mode & 0o777 == 0o600
    assert Path(env["BOOKER_BACKUP_DIR"]).stat().st_mode & 0o777 == 0o700
    assert b"SEALED_UPLOAD_MARKER" not in first.read_bytes()
    assert b"SEALED_DB_MARKER" not in first.read_bytes()
    assert not list(Path(env["BOOKER_BACKUP_DIR"]).glob("*.tar.gz"))
    assert not list(Path(env["BOOKER_BACKUP_DIR"]).glob(".staging-*"))
    key_id = subprocess.check_output(
        [CRYPTO_PY, str(ROOT / "infra" / "backup_crypto.py"), "key-id", str(key1)], text=True
    ).strip()
    archive_key_id = subprocess.check_output(
        [CRYPTO_PY, str(ROOT / "infra" / "backup_crypto.py"), "archive-key-id", str(first)],
        text=True,
    ).strip()
    assert archive_key_id == key_id
    restore1 = tmp_path / "restore-one"
    result = _restore(first, restore1, env)
    assert result.returncode == 0, result.stderr
    assert restore1.stat().st_mode & 0o777 == 0o700
    assert (restore1 / "uploads" / "sample.txt").read_text() == "SEALED_UPLOAD_MARKER"
    with sqlite3.connect(restore1 / "booker.db") as db:
        assert db.execute("SELECT id FROM users").fetchone()[0] == "SEALED_DB_MARKER"

    key2 = _key(tmp_path / "key-2")
    env2 = {**env, "BOOKER_BACKUP_KEY_FILE": str(key2)}
    second = _backup(env2)
    assert first != second and first.is_file()
    assert first.read_bytes()[:40] != second.read_bytes()[:40]
    assert _restore(first, tmp_path / "wrong-rotation", env2).returncode != 0
    assert not (tmp_path / "wrong-rotation").exists()
    assert _restore(first, tmp_path / "restore-old-key", env).returncode == 0
    assert _restore(second, tmp_path / "restore-new-key", env2).returncode == 0
    colocated_key = Path(env["BOOKER_BACKUP_DIR"]) / "unsafe-key"
    shutil.copyfile(key1, colocated_key)
    colocated_key.chmod(0o600)
    no_backup_dir_env = {**env, "BOOKER_BACKUP_KEY_FILE": str(colocated_key)}
    no_backup_dir_env.pop("BOOKER_BACKUP_DIR")
    assert _restore(first, tmp_path / "colocated-key-restore", no_backup_dir_env).returncode != 0
    assert not (tmp_path / "colocated-key-restore").exists()
    disguised = Path(env["BOOKER_BACKUP_DIR"]) / "sealed-with-targz-name.tar.gz"
    shutil.copyfile(second, disguised)
    strict_env = {**env2, "BOOKER_BACKUP_REQUIRE_SEALED_RESTORE": "1"}
    assert _restore(disguised, tmp_path / "restore-by-magic", strict_env).returncode == 0


def test_sealed_restore_rejects_wrong_key_and_tampering_before_target(tmp_path):
    key = _key(tmp_path / "key")
    env = _environment(tmp_path, key)
    archive = _backup(env)
    wrong_key = _key(tmp_path / "wrong-key")
    wrong_env = {**env, "BOOKER_BACKUP_KEY_FILE": str(wrong_key)}
    target = tmp_path / "wrong-key-restore"
    assert _restore(archive, target, wrong_env).returncode != 0
    assert not target.exists()

    original = archive.read_bytes()
    for label, offset in (
        ("magic", 0),
        ("key-id", 18),
        ("nonce", 30),
        ("ciphertext", len(original) // 2),
        ("tag", len(original) - 1),
    ):
        changed = bytearray(original)
        changed[offset] ^= 1
        tampered = tmp_path / f"{label}.bke"
        tampered.write_bytes(changed)
        target = tmp_path / f"restore-{label}"
        assert _restore(tampered, target, env).returncode != 0
        assert not target.exists()

    appended = tmp_path / "appended.bke"
    appended.write_bytes(original + b"extra")
    assert _restore(appended, tmp_path / "restore-appended", env).returncode != 0
    assert not (tmp_path / "restore-appended").exists()
    truncated = tmp_path / "truncated.bke"
    truncated.write_bytes(original[:-8])
    assert _restore(truncated, tmp_path / "restore-truncated", env).returncode != 0
    assert not (tmp_path / "restore-truncated").exists()


def test_sealed_key_permissions_and_legacy_policy(tmp_path):
    key = _key(tmp_path / "key")
    env = _environment(tmp_path, key)
    key.chmod(0o644)
    failed = subprocess.run(
        ["bash", str(ROOT / "infra" / "backup-booker.sh")], env=env, capture_output=True, check=False
    )
    assert failed.returncode != 0
    assert not list((tmp_path / "backups").glob("booker-*.bke"))
    key.chmod(0o600)
    linked = tmp_path / "linked-key"
    linked.symlink_to(key)
    linked_env = {**env, "BOOKER_BACKUP_KEY_FILE": str(linked)}
    assert subprocess.run(
        ["bash", str(ROOT / "infra" / "backup-booker.sh")],
        env=linked_env,
        capture_output=True,
        check=False,
    ).returncode != 0

    legacy_env = {**env, "BOOKER_BACKUP_FORMAT": "legacy"}
    legacy = _backup_legacy(legacy_env)
    strict = {**env, "BOOKER_BACKUP_REQUIRE_SEALED_RESTORE": "1"}
    target = tmp_path / "legacy-rejected"
    assert _restore(legacy, target, strict).returncode != 0
    assert not target.exists()
    assert _restore(legacy, tmp_path / "legacy-allowed", legacy_env).returncode == 0


def test_sealed_preflight_failure_and_size_limit_leave_no_archive(tmp_path):
    key = _key(tmp_path / "key")
    env = _environment(tmp_path, key)
    unavailable = tmp_path / "no-crypto"
    unavailable.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    unavailable.chmod(0o755)
    missing = subprocess.run(
        ["bash", str(ROOT / "infra" / "backup-booker.sh")],
        env={**env, "BOOKER_BACKUP_CRYPTO_PYTHON": str(unavailable)},
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0
    assert not list((tmp_path / "backups").glob("booker-*.bke"))
    limited = subprocess.run(
        ["bash", str(ROOT / "infra" / "backup-booker.sh")],
        env={**env, "BOOKER_BACKUP_MAX_RESTORE_BYTES": "1024"},
        capture_output=True,
        check=False,
    )
    assert limited.returncode != 0
    assert not list((tmp_path / "backups").glob("booker-*.bke"))
    assert not list((tmp_path / "backups").glob("*.partial"))
    nested_staging = subprocess.run(
        ["bash", str(ROOT / "infra" / "backup-booker.sh")],
        env={**env, "BOOKER_BACKUP_STAGING_PARENT": env["BOOKER_BACKUP_DIR"]},
        capture_output=True,
        check=False,
    )
    assert nested_staging.returncode != 0
    assert not list((tmp_path / "backups").glob("booker-*.bke"))


def test_sealed_retention_obeys_dry_run_then_deletes_old_archive(tmp_path):
    key = _key(tmp_path / "key")
    env = _environment(tmp_path, key)
    old = _backup(env)
    age = time.time() - 40 * 24 * 60 * 60
    os.utime(old, (age, age))
    dry_run = {**env, "BOOKER_BACKUP_RETENTION_DRY_RUN": "1"}
    _backup(dry_run)
    assert old.exists()
    _backup(env)
    assert not old.exists()


def _backup_legacy(env: dict[str, str]) -> Path:
    subprocess.run(["bash", str(ROOT / "infra" / "backup-booker.sh")], env=env, check=True)
    return next(Path(env["BOOKER_BACKUP_DIR"]).glob("booker-*.tar.gz"))
