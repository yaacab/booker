"""The identity expansion must preserve legacy users and never merge by email."""

import sqlite3

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import booker_api.models  # noqa: F401
from alembic import command
from booker_api.db import Base, run_migrations


def _insert_identity(connection, *, row_id: str, user_id: str, provider: str,
                     subject: str, provider_email: str | None = None) -> None:
    connection.execute(text(
        "INSERT INTO user_identities "
        "(id,user_id,provider,provider_subject,provider_email,provider_email_verified,"
        "link_origin,linked_at) VALUES "
        "(:id,:user_id,:provider,:subject,:email,1,'explicit_link',CURRENT_TIMESTAMP)"
    ), {"id": row_id, "user_id": user_id, "provider": provider,
        "subject": subject, "email": provider_email})


def test_identity_migration_preserves_legacy_user_and_enforces_subject_binding(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'identity.db'}"
    run_migrations(db_url)
    run_migrations(db_url)
    engine = create_engine(db_url)
    assert "user_identities" in inspect(engine).get_table_names()

    with engine.begin() as connection:
        for user_id, email in (("owner", "owner@booker.test"),
                               ("other", "other@booker.test")):
            connection.execute(text(
                "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
                "totp_enabled,created_at) VALUES "
                "(:id,:email,'Existing','existing-hash',0,0,CURRENT_TIMESTAMP)"
            ), {"id": user_id, "email": email})
        _insert_identity(connection, row_id="telegram", user_id="owner",
                         provider="telegram", subject="123456")
        _insert_identity(connection, row_id="vk", user_id="owner", provider="vk",
                         subject="vk-subject", provider_email="other@booker.test")

    with engine.connect() as connection:
        legacy = connection.execute(text(
            "SELECT email,password_hash,email_verified_at FROM users WHERE id='owner'"
        )).one()
        other = connection.execute(text(
            "SELECT email,email_verified_at FROM users WHERE id='other'"
        )).one()
        identities = connection.execute(text(
            "SELECT provider,user_id FROM user_identities ORDER BY provider"
        )).all()
    assert legacy == ("owner@booker.test", "existing-hash", None)
    assert other == ("other@booker.test", None)
    assert identities == [("telegram", "owner"), ("vk", "owner")]

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_identity(connection, row_id="takeover", user_id="other",
                         provider="telegram", subject="123456")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_identity(connection, row_id="duplicate-provider", user_id="owner",
                         provider="vk", subject="another-vk-subject")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_identity(connection, row_id="unknown-provider", user_id="owner",
                         provider="unknown", subject="subject")
    engine.dispose()


def test_fresh_metadata_and_alembic_identity_constraints_match(tmp_path):
    fresh = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(fresh)
    migrated_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    run_migrations(migrated_url)
    migrated = create_engine(migrated_url)
    names = ("id", "user_id", "provider", "provider_subject", "provider_email",
             "provider_email_verified", "provider_phone", "link_origin", "linked_at",
             "last_login_at")
    for engine in (fresh, migrated):
        inspector = inspect(engine)
        assert tuple(column["name"] for column in inspector.get_columns("user_identities")) == names
        assert len(inspector.get_foreign_keys("user_identities")) == 1
        assert len(inspector.get_unique_constraints("user_identities")) == 2
        assert len(inspector.get_check_constraints("user_identities")) == 3
        engine.dispose()


def test_copy_upgrade_preserves_existing_account_and_session(tmp_path):
    original = tmp_path / "existing.db"
    candidate = tmp_path / "candidate.db"
    config = Config("apps/api/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{original}")
    command.upgrade(config, "a08f90e12f34")
    with sqlite3.connect(original) as db:
        db.execute(
            "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
            "totp_enabled,created_at) VALUES "
            "('legacy','legacy@booker.test','Existing','existing-hash',0,0,CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO session_tokens (token,user_id,created_at) "
            "VALUES ('existing-session','legacy',CURRENT_TIMESTAMP)"
        )
    before = original.read_bytes()
    with sqlite3.connect(original) as source, sqlite3.connect(candidate) as target:
        source.backup(target)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{candidate}")
    command.upgrade(config, "head")

    assert original.read_bytes() == before
    with sqlite3.connect(candidate) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                "a11f23e45f67",
        )
        assert db.execute("SELECT email,password_hash FROM users WHERE id='legacy'").fetchone() == (
            "legacy@booker.test", "existing-hash",
        )
        assert db.execute("SELECT user_id FROM session_tokens WHERE token='existing-session'").fetchone() == (
            "legacy",
        )
        assert db.execute("SELECT COUNT(*) FROM user_identities").fetchone() == (0,)
