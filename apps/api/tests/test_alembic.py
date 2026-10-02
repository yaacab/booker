from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

import booker_api.db as database
import booker_api.models  # noqa: F401
from alembic import command
from booker_api.db import Base, enable_sqlite_foreign_keys, ensure_sqlite_columns, run_migrations


def _alembic_config(db_url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def test_postgres_startup_preserves_password_for_alembic(monkeypatch):
    url = URL.create(
        "postgresql+psycopg",
        username="booker",
        password="test%secret@value",
        host="127.0.0.1",
        database="booker",
    )
    captured = []
    monkeypatch.setattr(database, "run_migrations", captured.append)
    database.init_schema(SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), url=url))
    assert make_url(captured[0]).password == "test%secret@value"


def test_alembic_config_preserves_url_encoded_percent(monkeypatch):
    url = URL.create(
        "postgresql+psycopg",
        username="booker",
        password="test%secret@value",
        host="127.0.0.1",
        database="booker",
    )
    captured = []
    monkeypatch.setattr("alembic.command.upgrade", lambda cfg, _revision: captured.append(cfg))
    database.run_migrations(url.render_as_string(hide_password=False))
    assert make_url(captured[0].get_main_option("sqlalchemy.url")).password == "test%secret@value"


def test_alembic_baseline_matches_models(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    run_migrations(db_url)
    run_migrations(db_url)  # idempotent

    eng = create_engine(db_url)
    inspector = inspect(eng)
    actual = set(inspector.get_table_names()) - {"alembic_version"}
    assert actual == set(Base.metadata.tables.keys())


def test_alembic_session_token_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    run_migrations(db_url)

    eng = create_engine(db_url)
    cols = {c["name"] for c in inspect(eng).get_columns("session_tokens")}
    assert {"token", "user_id", "created_at", "admin_2fa_verified_at", "expires_at"} <= cols


def test_message_receipt_migration_backfills_legacy_rows_and_is_idempotent(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'message-receipt.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "f5b0c1d2e3f4")
    engine = create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO messages "
            "(id, conversation_id, sequence, kind, body, attribution_status, created_at) "
            "VALUES ('legacy-message', 'legacy-conversation', 1, 'system', 'Старое', "
            "'system', '2026-09-01 12:00:00')"
        ))
        connection.execute(text(
            "INSERT INTO messages "
            "(id, conversation_id, sequence, kind, body, attribution_status, created_at) "
            "VALUES ('legacy-future', 'legacy-conversation', 2, 'system', 'Сдвинутое', "
            "'system', '2099-01-01 12:00:00')"
        ))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT created_at, received_at FROM messages WHERE id = 'legacy-message'"
        )).one()
        future_is_capped = connection.execute(text(
            "SELECT received_at <= CURRENT_TIMESTAMP FROM messages "
            "WHERE id = 'legacy-future'"
        )).scalar_one()
    assert row[0] == row[1]
    assert future_is_capped == 1


def test_alembic_baseline_revision_exists():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = list(versions.glob("*_baseline.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "def upgrade()" in text
    assert "users" in text


def test_money_movement_migration_keeps_external_out_and_backfills_partial(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ledger-backfill.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "a3c4d5e6f7a8")
    engine = create_engine(db_url)
    with engine.begin() as connection:
        for payment_id, status, provider, amount in (
            ("stub-paid", "succeeded", "stub", 100),
            ("stub-partial", "partially_refunded", "stub", 100),
            ("external-old", "succeeded", "external", 100),
        ):
            connection.execute(
                text(
                    "INSERT INTO payments "
                    "(id, booking_id, amount_rub, status, provider, idempotency_key, created_at) "
                    "VALUES (:id, :booking, :amount, :status, :provider, :key, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": payment_id,
                    "booking": f"booking-{payment_id}",
                    "amount": amount,
                    "status": status,
                    "provider": provider,
                    "key": f"key-{payment_id}",
                },
            )
        connection.execute(
            text(
                "INSERT INTO refund_requests "
                "(id, payment_id, requested_by_user_id, amount_rub, reason, status, created_at) "
                "VALUES ('refund-partial', 'stub-partial', 'admin-1', 30, 'partial', "
                "'refunded', CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT payment_id, kind, direction, amount_rub FROM money_movements "
                "ORDER BY payment_id, kind"
            )
        ).all()
        external_status = connection.execute(
            text("SELECT status FROM payments WHERE id = 'external-old'")
        ).scalar_one()
    assert rows == [
        ("stub-paid", "capture", "credit", 100),
        ("stub-partial", "capture", "credit", 100),
        ("stub-partial", "refund", "debit", 30),
    ]
    assert external_status == "external_recorded"
    # The later draft-ack migration deliberately blocks unattended downgrade.
    with pytest.raises(RuntimeError, match="manual migration required"):
        command.downgrade(config, "a3c4d5e6f7a8")


def test_sqlite_init_path_installs_append_only_triggers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO money_movements "
                "(id, booking_id, payment_id, kind, direction, amount_rub, currency, provider, "
                "source_type, source_id, metadata_json, created_at) "
                "VALUES ('movement-1', 'booking-1', 'payment-1', 'capture', 'credit', 100, "
                "'RUB', 'stub', 'test', 'event-1', '{}', CURRENT_TIMESTAMP)"
            )
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE money_movements SET amount_rub = 101 WHERE id = 'movement-1'")
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("DELETE FROM money_movements WHERE id = 'movement-1'"))


def test_sqlite_init_path_guards_deal_attestations(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'attestations.db'}")
    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO offer_acknowledgements "
                "(id, offer_version_id, side, organization_id, actor_user_id, "
                "actor_role_snapshot, attribution_status, created_at) VALUES "
                "('ack-1', 'version-1', 'customer', 'org-1', 'user-1', 'owner', "
                "'attributed', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO contract_signatures "
                "(id, contract_id, side, organization_id, actor_user_id, "
                "actor_role_snapshot, auth_method, attribution_status, created_at) VALUES "
                "('signature-1', 'contract-1', 'supplier', 'org-2', 'user-2', 'owner', "
                "'otp', 'attributed', CURRENT_TIMESTAMP)"
            )
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE offer_acknowledgements SET side = 'supplier' WHERE id = 'ack-1'")
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("DELETE FROM contract_signatures WHERE id = 'signature-1'"))


def test_actor_attribution_migration_marks_legacy_actions(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'actor-attribution.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "d6f7a8b9c0d1")
    engine = create_engine(db_url)
    _insert_legacy_conversation(engine)
    command.upgrade(config, "ef5b6c7d8e9f")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO offer_versions "
                "(id, offer_id, honorarium_rub, commission_rate, commission_rub, total_rub, "
                "advance_rub, balance_rub, security_deposit_rub, currency, terms, "
                "customer_ack, supplier_ack, created_at) VALUES "
                "('version-legacy', 'offer-legacy', 100, 0, 0, 100, 100, 0, 0, 'RUB', '', "
                "1, 1, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text("UPDATE offers SET active_version_id = 'version-legacy' WHERE id = 'offer-legacy'")
        )
        connection.execute(
            text(
                "INSERT INTO contracts "
                "(id, booking_id, template_key, body, customer_signed, supplier_signed, "
                "otp_customer, otp_supplier) VALUES "
                "('contract-legacy', 'booking-legacy', 'legacy', 'body', 1, 1, NULL, NULL)"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        acknowledgements = connection.execute(
            text(
                "SELECT side, organization_id, actor_user_id, attribution_status "
                "FROM offer_acknowledgements ORDER BY side"
            )
        ).all()
        signatures = connection.execute(
            text(
                "SELECT side, organization_id, actor_user_id, auth_method, attribution_status "
                "FROM contract_signatures ORDER BY side"
            )
        ).all()
    assert acknowledgements == [
        ("customer", "customer-legacy", None, "legacy_unattributed"),
        ("supplier", "supplier-legacy", None, "legacy_unattributed"),
    ]
    assert signatures == [
        ("customer", "customer-legacy", None, "legacy", "legacy_unattributed"),
        ("supplier", "supplier-legacy", None, "legacy", "legacy_unattributed"),
    ]


def test_message_attribution_migration_marks_system_and_legacy_chat(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'message-attribution.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "d6f7a8b9c0d1")
    engine = create_engine(db_url)
    _insert_legacy_conversation(engine)
    command.upgrade(config, "f05c6d7e8f90")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO messages "
                "(id, conversation_id, sequence, author_user_id, kind, body, created_at) VALUES "
                "('message-chat', 'conversation-legacy', 2, NULL, 'chat', 'Legacy', CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, author_org_id, author_side, author_name_snapshot, attribution_status "
                "FROM messages ORDER BY id"
            )
        ).all()
    assert rows == [
        ("message-chat", None, None, None, "legacy_unattributed"),
        ("message-legacy", None, None, None, "system"),
    ]


def test_read_state_migration_preserves_only_unambiguous_organization(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'read-state-party.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "d6f7a8b9c0d1")
    engine = create_engine(db_url)
    _insert_legacy_conversation(engine)
    command.upgrade(config, "f16d7e8f901a")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, full_name, password_hash, is_platform_admin, totp_enabled, created_at) "
                "VALUES ('reader-single', 'single@example.test', 'Single', 'x', 0, 0, CURRENT_TIMESTAMP), "
                "('reader-dual', 'dual@example.test', 'Dual', 'x', 0, 0, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO team_members "
                "(id, user_id, organization_id, role, can_confirm_offer) VALUES "
                "('member-single', 'reader-single', 'customer-legacy', 'owner', 1), "
                "('member-dual-c', 'reader-dual', 'customer-legacy', 'owner', 1), "
                "('member-dual-s', 'reader-dual', 'supplier-legacy', 'manager', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conversation_read_states "
                "(id, conversation_id, user_id, last_read_sequence, read_at) VALUES "
                "('read-single', 'conversation-legacy', 'reader-single', 1, CURRENT_TIMESTAMP), "
                "('read-dual', 'conversation-legacy', 'reader-dual', 1, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "head")
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("conversation_read_states")
    }
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspect(engine).get_unique_constraints("conversation_read_states")
    }
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, user_id, organization_id, last_read_sequence "
                "FROM conversation_read_states ORDER BY id"
            )
        ).all()
    assert "organization_id" in columns
    assert ("conversation_id", "user_id", "organization_id") in unique_sets
    assert ("conversation_id", "user_id") not in unique_sets
    assert rows == [("read-single", "reader-single", "customer-legacy", 1)]


def test_sqlite_runtime_repairs_partial_read_state_unique(tmp_path):
    engine = enable_sqlite_foreign_keys(create_engine(f"sqlite:///{tmp_path / 'partial-read.db'}"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE conversation_read_states"))
        connection.execute(
            text(
                "CREATE TABLE conversation_read_states ("
                "id VARCHAR(36) PRIMARY KEY NOT NULL, "
                "conversation_id VARCHAR(36) NOT NULL REFERENCES conversations(id), "
                "user_id VARCHAR(36) NOT NULL REFERENCES users(id), "
                "organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id), "
                "last_read_sequence INTEGER NOT NULL DEFAULT 0, read_at DATETIME NOT NULL, "
                "UNIQUE (conversation_id, user_id), "
                "CONSTRAINT uq_conversation_read_state_party "
                "UNIQUE (conversation_id, user_id, organization_id))"
            )
        )

    ensure_sqlite_columns(engine)
    ensure_sqlite_columns(engine)
    inspector = inspect(engine)
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("conversation_read_states")
    }
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        violations = connection.execute(text("PRAGMA foreign_key_check")).all()
    assert ("conversation_id", "user_id", "organization_id") in unique_sets
    assert ("conversation_id", "user_id") not in unique_sets
    assert foreign_keys == 1
    assert violations == []


def _insert_legacy_conversation(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations (id, name, kind, city, created_at) VALUES "
                "('customer-legacy', 'Legacy customer', 'customer', 'Москва', CURRENT_TIMESTAMP), "
                "('supplier-legacy', 'Legacy supplier', 'artist', 'Москва', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO events "
                "(id, organization_id, title, city, event_date, guest_count, budget_rub, "
                "notes, status) VALUES ('event-legacy', 'customer-legacy', 'Legacy event', "
                "'Москва', CURRENT_TIMESTAMP, 10, NULL, '', 'Draft')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO requests "
                "(id, event_id, resource_type, resource_id, supplier_org_id, status, created_at) "
                "VALUES ('request-legacy', 'event-legacy', 'artist', 'artist-legacy', "
                "'supplier-legacy', 'Negotiation', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO offers (id, request_id, active_version_id, created_at) "
                "VALUES ('offer-legacy', 'request-legacy', NULL, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO bookings "
                "(id, event_id, offer_id, accepted_offer_version_id, slot_id, status, "
                "payout_pending, created_at) VALUES "
                "('booking-legacy', 'event-legacy', 'offer-legacy', NULL, 'slot-legacy', "
                "'Negotiation', 0, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conversations (id, booking_id) "
                "VALUES ('conversation-legacy', 'booking-legacy')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages "
                "(id, conversation_id, author_user_id, kind, body, created_at) VALUES "
                "('message-legacy', 'conversation-legacy', NULL, 'system', 'Старое сообщение', "
                "CURRENT_TIMESTAMP)"
            )
        )


def test_request_conversation_migration_preserves_booking_chat(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conversation-migration.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "d6f7a8b9c0d1")
    engine = create_engine(db_url)
    _insert_legacy_conversation(engine)

    command.upgrade(config, "head")

    columns = {column["name"]: column for column in inspect(engine).get_columns("conversations")}
    with engine.connect() as connection:
        conversation = connection.execute(
            text(
                "SELECT request_id, booking_id, customer_org_id, supplier_org_id, "
                "customer_name_snapshot, supplier_name_snapshot "
                "FROM conversations "
                "WHERE id = 'conversation-legacy'"
            )
        ).one()
        message = connection.execute(
            text("SELECT body FROM messages WHERE id = 'message-legacy'")
        ).scalar_one()
    assert columns["booking_id"]["nullable"] is True
    assert conversation == (
        "request-legacy",
        "booking-legacy",
        "customer-legacy",
        "supplier-legacy",
        "Legacy customer",
        "Legacy supplier",
    )
    assert message == "Старое сообщение"


def test_sqlite_runtime_upgrades_legacy_conversation_shape(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conversation-runtime.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "d6f7a8b9c0d1")
    engine = create_engine(db_url)
    _insert_legacy_conversation(engine)
    Base.metadata.create_all(engine)

    ensure_sqlite_columns(engine)

    columns = {column["name"]: column for column in inspect(engine).get_columns("conversations")}
    read_columns = {
        column["name"]
        for column in inspect(engine).get_columns("conversation_read_states")
    }
    read_unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspect(engine).get_unique_constraints("conversation_read_states")
    }
    with engine.connect() as connection:
        conversation = connection.execute(
            text(
                "SELECT request_id, booking_id, customer_org_id, supplier_org_id, "
                "customer_name_snapshot, supplier_name_snapshot "
                "FROM conversations "
                "WHERE id = 'conversation-legacy'"
            )
        ).one()
        message = connection.execute(
            text("SELECT body FROM messages WHERE id = 'message-legacy'")
        ).scalar_one()
    assert columns["booking_id"]["nullable"] is True
    assert conversation == (
        "request-legacy",
        "booking-legacy",
        "customer-legacy",
        "supplier-legacy",
        "Legacy customer",
        "Legacy supplier",
    )
    assert message == "Старое сообщение"
    assert "organization_id" in read_columns
    assert ("conversation_id", "user_id", "organization_id") in read_unique_sets


def test_sqlite_runtime_scopes_legacy_invitation_idempotency(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'invitation-runtime.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE organization_invitations"))
        connection.execute(
            text(
                "CREATE TABLE organization_invitations ("
                "id VARCHAR(36) PRIMARY KEY NOT NULL, organization_id VARCHAR(36) NOT NULL, "
                "email VARCHAR(255) NOT NULL, invited_user_id VARCHAR(36), role VARCHAR(32) NOT NULL, "
                "can_confirm_offer BOOLEAN NOT NULL, token_hash VARCHAR(64) NOT NULL UNIQUE, "
                "idempotency_key VARCHAR(64) NOT NULL UNIQUE, status VARCHAR(16) NOT NULL, "
                "invited_by_user_id VARCHAR(36) NOT NULL, expires_at DATETIME NOT NULL, "
                "accepted_at DATETIME, revoked_at DATETIME, created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO organization_invitations VALUES "
                "('invite-legacy', 'org-1', 'legacy@example.com', NULL, 'viewer', 0, "
                "'token-legacy', 'client-operation', 'accepted', 'user-1', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP)"
            )
        )

    ensure_sqlite_columns(engine)

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspect(engine).get_unique_constraints("organization_invitations")
    }
    with engine.connect() as connection:
        preserved = connection.execute(
            text(
                "SELECT id, idempotency_key, status FROM organization_invitations "
                "WHERE id = 'invite-legacy'"
            )
        ).one()
    assert preserved == ("invite-legacy", "client-operation", "accepted")
    assert ("organization_id", "invited_by_user_id", "idempotency_key") in unique_sets
    assert ("idempotency_key",) not in unique_sets


def test_support_runtime_schema_can_be_adopted_by_later_migrations(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'support-runtime-adoption.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "e7a8b9c0d1e2")
    engine = enable_sqlite_foreign_keys(create_engine(db_url))

    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    command.upgrade(config, "head")

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        triggers = {
            row[0]
            for row in connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ))
        }
    assert revision == "a04f56b78c90"
    assert {
        "contracts_offer_version_fk_insert",
        "contracts_offer_version_fk_update",
        "contract_signatures_offer_version_fk_insert",
        "contract_signatures_offer_version_fk_update",
    } <= triggers


def test_support_agent_migration_rejects_missing_feedback_uniqueness(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'support-incompatible-adoption.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "e8b9c0d1e2f3")
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE support_agent_feedback"))
        connection.execute(
            text(
                "CREATE TABLE support_agent_feedback ("
                "id VARCHAR(36) PRIMARY KEY, exchange_id VARCHAR(36) NOT NULL, "
                "user_id VARCHAR(36) NOT NULL, rating VARCHAR(16) NOT NULL, "
                "reason_code VARCHAR(32), comment TEXT NOT NULL, created_at DATETIME NOT NULL)"
            )
        )
    with pytest.raises(RuntimeError, match="incompatible support_agent_feedback"):
        command.upgrade(config, "e9c0d1e2f3a4")


def test_support_ticket_migration_rejects_missing_message_uniqueness(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'support-ticket-incompatible.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "e7a8b9c0d1e2")
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE support_messages"))
        connection.execute(
            text(
                "CREATE TABLE support_messages ("
                "id VARCHAR(36) PRIMARY KEY, ticket_id VARCHAR(36) NOT NULL, "
                "author_user_id VARCHAR(36) NOT NULL, author_kind VARCHAR(16) NOT NULL, "
                "body TEXT NOT NULL, idempotency_key_hash VARCHAR(64) NOT NULL, "
                "request_fingerprint VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL)"
            )
        )
    with pytest.raises(RuntimeError, match="incompatible support_messages"):
        command.upgrade(config, "e8b9c0d1e2f3")


def test_support_ticket_adoption_repairs_constraints_without_losing_rows(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'support-ticket-with-row.db'}"
    config = _alembic_config(db_url)
    command.upgrade(config, "e7a8b9c0d1e2")
    engine = create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, full_name, password_hash, is_platform_admin, totp_enabled, created_at) "
                "VALUES ('pilot-user', 'pilot@booker.test', 'Pilot', 'hash', 0, 0, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO support_tickets "
                "(id, author_user_id, category, subject, body, status, created_at) "
                "VALUES ('kept-ticket', 'pilot-user', 'technical', 'Help', 'Body', "
                "'open', CURRENT_TIMESTAMP)"
            )
        )
    Base.metadata.create_all(engine)
    ensure_sqlite_columns(engine)
    command.upgrade(config, "e8b9c0d1e2f3")
    with engine.connect() as connection:
        kept = connection.execute(
            text("SELECT id, body FROM support_tickets WHERE id = 'kept-ticket'")
        ).one()
    unique_sets = {
        frozenset(item.get("column_names") or [])
        for item in inspect(engine).get_unique_constraints("support_tickets")
    }
    assert kept == ("kept-ticket", "Body")
    assert frozenset({"author_user_id", "idempotency_key_hash"}) in unique_sets


def test_sqlite_migrations_enable_support_foreign_keys(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'support-fk.db'}"
    run_migrations(db_url)
    engine = enable_sqlite_foreign_keys(create_engine(db_url))
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO support_agent_exchanges "
                "(id, session_id, user_message, assistant_message, intent, outcome, "
                "needs_human, source_ids_json, idempotency_key_hash, request_fingerprint, "
                "created_at) VALUES ('orphan', 'missing-session', 'q', 'a', 'technical', "
                "'answered', 0, '[]', 'key', 'fingerprint', CURRENT_TIMESTAMP)"
            )
        )
