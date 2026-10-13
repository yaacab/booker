"""Legal ledger migration constraints and SQLite immutability guards."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from booker_api.db import Base, ensure_sqlite_columns, init_schema

REVISION = "feab012bc3d5"


def _config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_legal_ledger_upgrade_guards_and_nonempty_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'legal-ledger.db'}"
    config = _config(url)
    command.upgrade(config, REVISION)
    engine = create_engine(url)
    init_schema(engine)  # migration and runtime definitions must agree
    assert {"legal_document_versions", "consent_events"} <= set(inspect(engine).get_table_names())
    assert "marketing_consent_active" in {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM legal_document_versions")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM consent_events")).scalar_one() == 0
        conn.execute(text(
            "INSERT INTO users (id, email, full_name, password_hash, is_platform_admin, "
            "totp_enabled, optional_processing_restricted, created_at) "
            "VALUES ('u1', 'legal@test.invalid', 'Legal', 'test', 0, 0, 0, CURRENT_TIMESTAMP)"
        ))
        assert conn.execute(text(
            "SELECT marketing_consent_active FROM users WHERE id = 'u1'"
        )).scalar_one() == 0
        conn.execute(text(
            "INSERT INTO legal_document_versions "
            "(id, key, version, content_hash, status, source_path, created_at) "
            "VALUES ('d1', 'offer', 'v1', :hash, 'draft', 'docs/legal/OFFER_DRAFT.md', CURRENT_TIMESTAMP)"
        ), {"hash": "a" * 64})
        conn.execute(text(
            "UPDATE legal_document_versions SET status = 'published', "
            "published_at = CURRENT_TIMESTAMP WHERE id = 'd1'"
        ))
        conn.execute(text(
            "INSERT INTO consent_events (id, user_id, kind, document_version_id, "
            "document_version, document_hash, action, channel, created_at, metadata_json) "
            "VALUES ('c1', 'u1', 'offer', 'd1', 'v1', :hash, 'accepted', "
            "'registration', CURRENT_TIMESTAMP, '{}')"
        ), {"hash": "a" * 64})

    forbidden = (
        "UPDATE legal_document_versions SET content_hash = '" + "b" * 64 + "' WHERE id = 'd1'",
        "UPDATE legal_document_versions SET version = 'v2' WHERE id = 'd1'",
        "UPDATE legal_document_versions SET source_path = 'changed' WHERE id = 'd1'",
        "DELETE FROM legal_document_versions WHERE id = 'd1'",
        "INSERT INTO legal_document_versions (id, key, version, content_hash, status, "
        "source_path, created_at, published_at) VALUES "
        "('d2', 'offer', 'v2', '" + "b" * 64 + "', 'published', 'source', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        "UPDATE consent_events SET action = 'withdrawn' WHERE id = 'c1'",
        "DELETE FROM consent_events WHERE id = 'c1'",
    )
    for statement in forbidden:
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(text(statement))

    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE legal_document_versions SET status = 'retired', "
            "retired_at = CURRENT_TIMESTAMP WHERE id = 'd1'"
        ))
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("UPDATE legal_document_versions SET status = 'published' WHERE id = 'd1'"))
    with pytest.raises(RuntimeError, match="Refusing to drop consent history"):
        command.downgrade(config, "fd9a012bc3d4")


def test_sqlite_runtime_tables_are_adopted_with_guards(tmp_path):
    url = f"sqlite:///{tmp_path / 'legal-runtime.db'}"
    config = _config(url)
    command.upgrade(config, "fd9a012bc3d4")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    command.upgrade(config, REVISION)
    with engine.connect() as conn:
        indexes = {row[0] for row in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'legal_document_versions'"
        ))}
        triggers = {row[0] for row in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND tbl_name = 'consent_events'"
        ))}
        assert "uq_legal_document_published_key" in indexes
        assert {"consent_events_no_update", "consent_events_no_delete"} <= triggers


def test_sqlite_init_schema_installs_legal_guards_without_alembic(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime-legal.db'}")
    init_schema(engine)
    init_schema(engine)  # idempotent; existing trigger SQL must still match
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, full_name, password_hash, is_platform_admin, "
            "totp_enabled, optional_processing_restricted, marketing_consent_active, created_at) "
            "VALUES ('u1', 'runtime-legal@test.invalid', 'Legal', 'test', 0, 0, 0, 0, "
            "CURRENT_TIMESTAMP)"
        ))
        conn.execute(text(
            "INSERT INTO legal_document_versions "
            "(id, key, version, content_hash, status, source_path, created_at) "
            "VALUES ('d1', 'offer', 'v1', :hash, 'draft', 'docs/legal/OFFER_DRAFT.md', "
            "CURRENT_TIMESTAMP)"
        ), {"hash": "a" * 64})
        conn.execute(text(
            "UPDATE legal_document_versions SET status = 'published', "
            "published_at = CURRENT_TIMESTAMP WHERE id = 'd1'"
        ))
        conn.execute(text(
            "INSERT INTO consent_events (id, user_id, kind, document_version_id, "
            "document_version, document_hash, action, channel, created_at, metadata_json) "
            "VALUES ('c1', 'u1', 'offer', 'd1', 'v1', :hash, 'accepted', "
            "'registration', CURRENT_TIMESTAMP, '{}')"
        ), {"hash": "a" * 64})
    for sql in (
        "UPDATE consent_events SET action = 'withdrawn' WHERE id = 'c1'",
        "DELETE FROM consent_events WHERE id = 'c1'",
        "UPDATE legal_document_versions SET content_hash = '" + "b" * 64 + "' WHERE id = 'd1'",
        "DELETE FROM legal_document_versions WHERE id = 'd1'",
    ):
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(text(sql))


def test_sqlite_init_schema_rejects_tampered_legal_guard(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tampered-legal.db'}")
    init_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER consent_events_no_update"))
        conn.execute(text(
            "CREATE TRIGGER consent_events_no_update BEFORE UPDATE ON consent_events "
            "BEGIN SELECT 1; END"
        ))
    with pytest.raises(RuntimeError, match="SQLite legal ledger guard mismatch"):
        init_schema(engine)
