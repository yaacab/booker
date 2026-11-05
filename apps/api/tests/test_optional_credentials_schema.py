"""External-only accounts must not change or disable legacy account guards."""

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import booker_api.models  # noqa: F401
from alembic import command
from booker_api.db import Base
from booker_api.models import User, UserIdentity
from booker_api.security import issue_token, verify_password
from tests.conftest import auth_header


def _triggers(db: sqlite3.Connection) -> dict[str, str]:
    return dict(db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='users'"
    ).fetchall())


def _named_indexes(db: sqlite3.Connection) -> dict[str, str]:
    return dict(db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='users' "
        "AND sql IS NOT NULL"
    ).fetchall())


def test_optional_credentials_copy_upgrade_preserves_legacy_account_and_guards(tmp_path):
    original = tmp_path / "legacy.db"
    candidate = tmp_path / "candidate.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{original}")
    command.upgrade(config, "a09f01e23f45")
    with sqlite3.connect(original) as db:
        db.execute(
            "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
            "totp_enabled,created_at) VALUES "
            "('legacy','legacy@booker.test','Legacy','legacy-hash',0,0,CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO session_tokens (token,user_id,created_at) "
            "VALUES ('legacy-session','legacy',CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO user_identities (id,user_id,provider,provider_subject,link_origin,"
            "linked_at) VALUES ('legacy-binding','legacy','telegram','legacy-tg',"
            "'explicit_link',CURRENT_TIMESTAMP)"
        )
        before_triggers = _triggers(db)
        before_indexes = _named_indexes(db)
    before_bytes = original.read_bytes()
    with sqlite3.connect(original) as source, sqlite3.connect(candidate) as target:
        source.backup(target)

    config.set_main_option("sqlalchemy.url", f"sqlite:///{candidate}")
    command.upgrade(config, "head")
    assert original.read_bytes() == before_bytes
    with sqlite3.connect(candidate) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert _triggers(db) == before_triggers
        assert _named_indexes(db) == before_indexes
        assert db.execute(
            "SELECT email,password_hash FROM users WHERE id='legacy'"
        ).fetchone() == ("legacy@booker.test", "legacy-hash")
        assert db.execute(
            "SELECT user_id FROM session_tokens WHERE token='legacy-session'"
        ).fetchone() == ("legacy",)
        assert db.execute(
            "SELECT user_id,provider,provider_subject,link_origin FROM user_identities "
            "WHERE id='legacy-binding'"
        ).fetchone() == ("legacy", "telegram", "legacy-tg", "explicit_link")
        db.execute(
            "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
            "totp_enabled,created_at) VALUES "
            "('external',NULL,'External',NULL,0,0,CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO user_identities (id,user_id,provider,provider_subject,link_origin,"
            "linked_at) VALUES ('binding','external','telegram','tg-123','first_login',"
            "CURRENT_TIMESTAMP)"
        )
        assert db.execute("SELECT email_verified_at FROM users WHERE id='external'").fetchone() == (None,)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE users SET is_platform_admin=1 WHERE id='external'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE users SET email_verified_at=CURRENT_TIMESTAMP WHERE id='external'"
            )
        assert not verify_password("anything", None)


def test_fresh_metadata_allows_external_only_user(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    columns = {row["name"]: row for row in inspect(engine).get_columns("users")}
    assert columns["email"]["nullable"]
    assert columns["password_hash"]["nullable"]
    engine.dispose()


def test_external_only_account_projects_null_email_without_claiming_proof(client, SessionLocal):
    with SessionLocal() as db:
        user = User(email=None, password_hash=None, full_name="External User")
        db.add(user)
        db.flush()
        db.add(UserIdentity(
            user_id=user.id, provider="telegram", provider_subject="987654321",
            link_origin="first_login",
        ))
        token = issue_token(db, user)
        db.commit()
    me = client.get("/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] is None
    assert me.json()["email_verified"] is False
    assert client.post(
        "/auth/login", json={"email": "external@booker.test", "password": "anything"}
    ).status_code == 401
