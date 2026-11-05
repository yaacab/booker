"""TOTP secrets must be encrypted at rest across new and migrated accounts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from booker_api.config import settings, validate_runtime_config
from booker_api.db import Base, init_schema
from booker_api.models import User
from booker_api.totp_storage import decrypt_totp_secret, encrypt_totp_secret
from tests.totp_helpers import TEST_TOTP_SECRET


def _config(path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return config


def test_new_user_stores_only_ciphertext_and_orm_keeps_totp_working(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="encrypted@booker.test", full_name="Encrypted",
                    password_hash="fixture", totp_enabled=True, totp_secret=TEST_TOTP_SECRET)
        db.add(user)
        db.commit()
        user_id = user.id
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT totp_secret FROM users WHERE id = :id"),
                              {"id": user_id}).scalar_one()
    assert stored.startswith("fernet:v1:")
    assert TEST_TOTP_SECRET not in stored
    assert decrypt_totp_secret(stored) == TEST_TOTP_SECRET
    with Session(engine) as db:
        assert db.get(User, user_id).totp_secret == TEST_TOTP_SECRET


def test_fresh_runtime_schema_rejects_plaintext_direct_sql(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    init_schema(engine)
    with engine.begin() as conn, pytest.raises(IntegrityError, match="encrypted"):
        conn.execute(text(
            "INSERT INTO users (id, email, full_name, password_hash, "
            "is_platform_admin, is_support_operator, totp_enabled, totp_secret, "
            "email_verified_at, created_at) VALUES "
            "('raw-admin', 'raw@booker.test', 'Raw', 'fixture', 1, 0, 1, "
            ":raw, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"raw": TEST_TOTP_SECRET})


def test_ciphertext_rejects_plaintext_wrong_key_and_tampering(monkeypatch):
    stored = encrypt_totp_secret(TEST_TOTP_SECRET)
    with pytest.raises(RuntimeError, match="requires migration"):
        decrypt_totp_secret(TEST_TOTP_SECRET)
    with pytest.raises(RuntimeError, match="unreadable"):
        decrypt_totp_secret(stored[:-2] + "xx")
    monkeypatch.setattr(settings, "totp_encryption_keys", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="unreadable"):
        decrypt_totp_secret(stored)


def test_key_rotation_reads_old_and_writes_with_new_primary(monkeypatch):
    old_key = Fernet.generate_key().decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "totp_encryption_keys", old_key)
    old_stored = encrypt_totp_secret(TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "totp_encryption_keys", f"{new_key},{old_key}")
    assert decrypt_totp_secret(old_stored) == TEST_TOTP_SECRET
    new_stored = encrypt_totp_secret(TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "totp_encryption_keys", new_key)
    assert decrypt_totp_secret(new_stored) == TEST_TOTP_SECRET
    with pytest.raises(RuntimeError, match="unreadable"):
        decrypt_totp_secret(old_stored)


def test_production_requires_explicit_valid_key(monkeypatch):
    monkeypatch.setattr(settings, "runtime_env", "production")
    monkeypatch.setattr(settings, "totp_encryption_keys", "")
    with pytest.raises(RuntimeError, match="not configured"):
        encrypt_totp_secret(TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "totp_encryption_keys", "invalid")
    with pytest.raises(RuntimeError, match="invalid"):
        encrypt_totp_secret(TEST_TOTP_SECRET)
    with pytest.raises(RuntimeError, match="BOOKER_TOTP_ENCRYPTION_KEYS"):
        validate_runtime_config(settings)


def test_staging_rejects_test_fallback_key():
    with pytest.raises(RuntimeError, match="BOOKER_TOTP_ENCRYPTION_KEYS"):
        validate_runtime_config(type(settings)(runtime_env="staging", totp_encryption_keys=""))


def test_migration_backfills_legacy_raw_secret_and_guards_sqlite(tmp_path):
    path = tmp_path / "legacy.db"
    config = _config(path)
    command.upgrade(config, "a03f45a67b89")
    already_encrypted = encrypt_totp_secret(TEST_TOTP_SECRET)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (id, email, full_name, password_hash, "
            "is_platform_admin, is_support_operator, totp_enabled, totp_secret, "
            "email_verified_at, created_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("legacy-admin", "legacy@booker.test", "Legacy", "fixture", TEST_TOTP_SECRET),
        )
        db.execute(
            "INSERT INTO users (id, email, full_name, password_hash, "
            "is_platform_admin, is_support_operator, totp_enabled, totp_secret, "
            "email_verified_at, created_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("already-encrypted", "encrypted-old@booker.test", "Existing", "fixture",
             already_encrypted),
        )
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        stored = db.execute("SELECT totp_secret FROM users WHERE id = 'legacy-admin'").fetchone()[0]
        assert stored.startswith("fernet:v1:") and TEST_TOTP_SECRET not in stored
        assert decrypt_totp_secret(stored) == TEST_TOTP_SECRET
        assert db.execute("SELECT totp_secret FROM users WHERE id = 'already-encrypted'").fetchone()[0] == already_encrypted
        with pytest.raises(sqlite3.IntegrityError, match="encrypted"):
            db.execute("UPDATE users SET totp_secret = ? WHERE id = 'legacy-admin'",
                       (TEST_TOTP_SECRET,))
    command.upgrade(config, "head")


@pytest.mark.parametrize("legacy_secret", ["invalid", "A" * 17])
def test_migration_blocks_unknown_legacy_secret_without_stamping(tmp_path, legacy_secret):
    path = tmp_path / "invalid-legacy.db"
    config = _config(path)
    command.upgrade(config, "a03f45a67b89")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (id, email, full_name, password_hash, "
            "is_platform_admin, is_support_operator, totp_enabled, totp_secret, "
            "email_verified_at, created_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("invalid-admin", "invalid@booker.test", "Invalid", "fixture", legacy_secret),
        )
    with pytest.raises(RuntimeError, match="manual review"):
        command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "a03f45a67b89"
