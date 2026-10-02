from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from booker_api.config import settings


class Base(DeclarativeBase):
    pass


def enable_sqlite_foreign_keys(bind: Engine) -> Engine:
    """Enable SQLite FK checks on every application, migration, and test connection."""

    if bind.dialect.name != "sqlite" or getattr(bind, "_booker_fk_hook", False):
        return bind

    @event.listens_for(bind, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    bind._booker_fk_hook = True  # type: ignore[attr-defined]
    return bind


def _add_column_if_missing(bind, table: str, column: str, ddl: str) -> None:
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        return
    with bind.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def ensure_missing_columns(bind) -> None:
    """Backfill columns on existing SQLite or Postgres tables. create_all does not ALTER."""
    dialect = bind.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        return
    has_services = "services" in inspect(bind).get_table_names()
    _add_column_if_missing(bind, "services", "resource_type", "resource_type VARCHAR(16)")
    _add_column_if_missing(bind, "services", "resource_id", "resource_id VARCHAR(36)")
    if has_services:
        with bind.begin() as conn:
            conn.execute(text(
                "UPDATE services SET resource_type = 'artist', "
                "resource_id = (SELECT id FROM artists WHERE artists.organization_id = services.organization_id) "
                "WHERE resource_id IS NULL AND "
                "(SELECT COUNT(*) FROM artists WHERE artists.organization_id = services.organization_id) = 1 "
                "AND (SELECT COUNT(*) FROM venues WHERE venues.organization_id = services.organization_id) = 0 "
                "AND services.category_code = "
                "(SELECT category FROM artists WHERE artists.organization_id = services.organization_id)"
            ))
            conn.execute(text(
                "UPDATE services SET resource_type = 'venue', "
                "resource_id = (SELECT id FROM venues WHERE venues.organization_id = services.organization_id) "
                "WHERE resource_id IS NULL AND "
                "(SELECT COUNT(*) FROM venues WHERE venues.organization_id = services.organization_id) = 1 "
                "AND (SELECT COUNT(*) FROM artists WHERE artists.organization_id = services.organization_id) = 0 "
                "AND services.category_code = 'venue'"
            ))
    _add_column_if_missing(bind, "users", "active_organization_id", "active_organization_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "users", "optional_processing_restricted",
        "optional_processing_restricted BOOLEAN NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        bind, "users", "marketing_consent_active",
        "marketing_consent_active BOOLEAN NOT NULL DEFAULT 0",
    )
    ts_type = "TIMESTAMPTZ" if dialect == "postgresql" else "DATETIME"
    _add_column_if_missing(
        bind, "users", "email_verification_required_at",
        f"email_verification_required_at {ts_type}",
    )
    _add_column_if_missing(
        bind, "users", "email_verified_at", f"email_verified_at {ts_type}",
    )
    _add_column_if_missing(
        bind, "users", "is_support_operator",
        "is_support_operator BOOLEAN NOT NULL DEFAULT FALSE",
    )
    _add_column_if_missing(
        bind, "availability_slots", "buffer_before_min", "buffer_before_min INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "availability_slots", "buffer_after_min", "buffer_after_min INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "availability_slots", "external_uid", "external_uid VARCHAR(255)"
    )
    _add_column_if_missing(bind, "requests", "requirement_id", "requirement_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "artists", "media_rights_status", "media_rights_status VARCHAR(32) DEFAULT 'unknown'"
    )
    _add_column_if_missing(bind, "artists", "media_source_url", "media_source_url VARCHAR(512)")
    _add_column_if_missing(
        bind, "artists", "media_rights_attested_at", f"media_rights_attested_at {ts_type}"
    )
    _add_column_if_missing(
        bind,
        "artists",
        "media_rights_attested_by_user_id",
        "media_rights_attested_by_user_id VARCHAR(36)",
    )
    _add_column_if_missing(
        bind, "artists", "calendar_confirmed_through", f"calendar_confirmed_through {ts_type}"
    )
    _add_column_if_missing(
        bind, "venues", "calendar_confirmed_through", f"calendar_confirmed_through {ts_type}"
    )
    _add_column_if_missing(
        bind, "artists", "calendar_confirmed_at", f"calendar_confirmed_at {ts_type}"
    )
    _add_column_if_missing(
        bind, "artists", "calendar_confirmed_by_user_id", "calendar_confirmed_by_user_id VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "artists", "publication_enabled", "publication_enabled BOOLEAN DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "artists", "publication_state_version", "publication_state_version INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "venues", "calendar_confirmed_at", f"calendar_confirmed_at {ts_type}"
    )
    _add_column_if_missing(
        bind, "venues", "calendar_confirmed_by_user_id", "calendar_confirmed_by_user_id VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "venues", "publication_enabled", "publication_enabled BOOLEAN DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "venues", "publication_state_version", "publication_state_version INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "venue_photos", "rights_attested_at", f"rights_attested_at {ts_type}"
    )
    _add_column_if_missing(
        bind, "venue_photos", "rights_attested_by_user_id", "rights_attested_by_user_id VARCHAR(36)"
    )
    with bind.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_artists_calendar_confirmed_through "
                "ON artists(calendar_confirmed_through)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_venues_calendar_confirmed_through "
                "ON venues(calendar_confirmed_through)"
            )
        )
    _add_column_if_missing(
        bind,
        "session_tokens",
        "admin_2fa_verified_at",
        f"admin_2fa_verified_at {ts_type}",
    )
    _add_column_if_missing(
        bind,
        "session_tokens",
        "expires_at",
        f"expires_at {ts_type}",
    )
    _add_column_if_missing(
        bind, "bookings", "accepted_offer_version_id", "accepted_offer_version_id VARCHAR(36)"
    )
    _add_column_if_missing(bind, "contracts", "offer_version_id", "offer_version_id VARCHAR(36)")
    _add_column_if_missing(bind, "contracts", "body_sha256", "body_sha256 VARCHAR(64)")
    _add_column_if_missing(
        bind, "contracts", "effect", "effect VARCHAR(48) NOT NULL DEFAULT 'legacy_unbound'"
    )
    _add_column_if_missing(
        bind, "contracts", "legal_pack_version",
        "legal_pack_version VARCHAR(48) NOT NULL DEFAULT 'legacy_unknown'",
    )
    _add_column_if_missing(
        bind, "contract_signatures", "offer_version_id", "offer_version_id VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "contract_signatures", "body_sha256", "body_sha256 VARCHAR(64)"
    )
    _add_column_if_missing(
        bind, "contract_signatures", "effect",
        "effect VARCHAR(48) NOT NULL DEFAULT 'legacy_unbound'",
    )
    _add_column_if_missing(bind, "offer_versions", "advance_rub", "advance_rub INTEGER DEFAULT 0")
    _add_column_if_missing(bind, "offer_versions", "balance_rub", "balance_rub INTEGER DEFAULT 0")
    _add_column_if_missing(
        bind,
        "offer_versions",
        "security_deposit_rub",
        "security_deposit_rub INTEGER DEFAULT 0",
    )
    _add_column_if_missing(
        bind,
        "offer_versions",
        "payment_terms_json",
        "payment_terms_json TEXT DEFAULT '{}'",
    )
    _add_column_if_missing(bind, "payments", "obligation_id", "obligation_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "payments", "provider_reference", "provider_reference VARCHAR(128)"
    )
    _add_column_if_missing(
        bind, "payments", "external_evidence_version", "external_evidence_version INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "payments", "provider_merchant", "provider_merchant VARCHAR(128) DEFAULT ''"
    )
    _add_column_if_missing(bind, "bookings", "payout_blocked", "payout_blocked BOOLEAN DEFAULT 0")
    _add_column_if_missing(
        bind, "bookings", "payout_block_reason", "payout_block_reason VARCHAR(64) DEFAULT ''"
    )
    _add_column_if_missing(
        bind,
        "payment_obligations",
        "grace_until",
        f"grace_until {ts_type}",
    )
    _add_column_if_missing(
        bind,
        "payment_obligations",
        "required_before_check_in",
        "required_before_check_in BOOLEAN DEFAULT 0",
    )
    _add_column_if_missing(bind, "conversations", "request_id", "request_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "conversations", "customer_org_id", "customer_org_id VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "conversations", "supplier_org_id", "supplier_org_id VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "conversations", "customer_name_snapshot", "customer_name_snapshot VARCHAR(255)"
    )
    _add_column_if_missing(
        bind, "conversations", "supplier_name_snapshot", "supplier_name_snapshot VARCHAR(255)"
    )
    _add_column_if_missing(
        bind, "conversations", "next_message_sequence", "next_message_sequence INTEGER DEFAULT 1"
    )
    _add_column_if_missing(bind, "messages", "idempotency_key", "idempotency_key VARCHAR(64)")
    _add_column_if_missing(bind, "messages", "received_at", f"received_at {ts_type}")
    if "messages" in inspect(bind).get_table_names():
        with bind.begin() as conn:
            conn.execute(text(
                "UPDATE messages SET received_at = CASE "
                "WHEN created_at > CURRENT_TIMESTAMP THEN CURRENT_TIMESTAMP "
                "ELSE created_at END WHERE received_at IS NULL"
            ))
    _add_column_if_missing(bind, "messages", "sequence", "sequence INTEGER")
    _add_column_if_missing(bind, "messages", "author_org_id", "author_org_id VARCHAR(36)")
    _add_column_if_missing(bind, "messages", "author_side", "author_side VARCHAR(16)")
    _add_column_if_missing(
        bind, "messages", "author_name_snapshot", "author_name_snapshot VARCHAR(255)"
    )
    _add_column_if_missing(
        bind, "messages", "actor_role_snapshot", "actor_role_snapshot VARCHAR(32)"
    )
    _add_column_if_missing(
        bind,
        "messages",
        "attribution_status",
        "attribution_status VARCHAR(32) DEFAULT 'legacy_unattributed' NOT NULL",
    )
    if "messages" in inspect(bind).get_table_names():
        with bind.begin() as conn:
            conn.execute(
                text(
                    "UPDATE messages SET attribution_status = 'system' "
                    "WHERE kind = 'system' AND attribution_status = 'legacy_unattributed'"
                )
            )
    read_state_has_sequence = (
        "conversation_read_states" in inspect(bind).get_table_names()
        and "last_read_sequence" in {
            column["name"]
            for column in inspect(bind).get_columns("conversation_read_states")
        }
    )
    _add_column_if_missing(
        bind,
        "conversation_read_states",
        "last_read_sequence",
        "last_read_sequence INTEGER DEFAULT 0",
    )
    _add_column_if_missing(bind, "venues", "address", "address VARCHAR(512) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "district", "district VARCHAR(128) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "metro", "metro VARCHAR(128) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "description", "description TEXT DEFAULT ''")
    _add_column_if_missing(bind, "venues", "source_url", "source_url VARCHAR(512) DEFAULT ''")
    _add_column_if_missing(
        bind, "venues", "source_attribution", "source_attribution VARCHAR(128) DEFAULT ''"
    )
    _add_column_if_missing(
        bind, "venues", "listing_origin", "listing_origin VARCHAR(32) DEFAULT 'owner'"
    )
    _add_column_if_missing(
        bind, "venues", "availability_mode", "availability_mode VARCHAR(32) DEFAULT 'owner'"
    )
    _add_column_if_missing(bind, "venues", "venue_type", "venue_type VARCHAR(64) DEFAULT ''")
    _add_column_if_missing(
        bind,
        "venues",
        "administrative_district",
        "administrative_district VARCHAR(32) DEFAULT ''",
    )
    _add_column_if_missing(bind, "venues", "latitude", "latitude FLOAT")
    _add_column_if_missing(bind, "venues", "longitude", "longitude FLOAT")
    _add_column_if_missing(bind, "venues", "phone", "phone VARCHAR(64) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "email", "email VARCHAR(255) DEFAULT ''")
    _add_column_if_missing(
        bind, "venues", "official_website", "official_website VARCHAR(512) DEFAULT ''"
    )
    _add_column_if_missing(
        bind, "venues", "source_type", "source_type VARCHAR(32) DEFAULT 'owner_submission'"
    )
    _add_column_if_missing(
        bind, "venues", "partnership_status", "partnership_status VARCHAR(32) DEFAULT 'claimed'"
    )
    _add_column_if_missing(bind, "venues", "is_partner", "is_partner BOOLEAN DEFAULT 0")
    _add_column_if_missing(bind, "venues", "is_claimed", "is_claimed BOOLEAN DEFAULT 1")
    _add_column_if_missing(
        bind, "venues", "moderation_status", "moderation_status VARCHAR(32) DEFAULT 'published'"
    )
    _add_column_if_missing(
        bind, "venues", "completeness_score", "completeness_score INTEGER DEFAULT 0"
    )
    _add_column_if_missing(bind, "venues", "details_json", "details_json TEXT DEFAULT '{}'")
    _add_column_if_missing(bind, "venues", "verified_at", f"verified_at {ts_type}")
    _add_column_if_missing(bind, "venues", "verified_by", "verified_by VARCHAR(36)")
    _add_column_if_missing(
        bind, "venues", "partnership_started_at", f"partnership_started_at {ts_type}"
    )
    _add_column_if_missing(bind, "venues", "status_changed_at", f"status_changed_at {ts_type}")
    _add_column_if_missing(bind, "venues", "last_verified_at", f"last_verified_at {ts_type}")
    _add_column_if_missing(bind, "venues", "last_crawled_at", f"last_crawled_at {ts_type}")
    _add_column_if_missing(
        bind,
        "venues",
        "data_freshness_status",
        "data_freshness_status VARCHAR(32) DEFAULT 'needs_review'",
    )
    _add_column_if_missing(
        bind,
        "deal_attachments",
        "scan_status",
        "scan_status VARCHAR(32) DEFAULT 'quarantined'",
    )
    _add_column_if_missing(bind, "deal_attachments", "scan_note", "scan_note TEXT DEFAULT ''")
    _add_column_if_missing(
        bind, "deal_attachments", "av_verdict_provider", "av_verdict_provider VARCHAR(32)"
    )
    _add_column_if_missing(
        bind, "deal_attachments", "av_verdict_sha256", "av_verdict_sha256 VARCHAR(64)"
    )
    _add_column_if_missing(bind, "deal_attachments", "av_scan_token", "av_scan_token VARCHAR(36)")
    _add_column_if_missing(bind, "deal_attachments", "av_scan_started_at", f"av_scan_started_at {ts_type}")
    _add_column_if_missing(
        bind, "deal_attachments", "scanned_by_user_id", "scanned_by_user_id VARCHAR(36)"
    )
    _add_column_if_missing(bind, "deal_attachments", "scanned_at", f"scanned_at {ts_type}")
    _add_column_if_missing(bind, "disputes", "opened_by_user_id", "opened_by_user_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "disputes", "assigned_to_user_id", "assigned_to_user_id VARCHAR(36)"
    )
    _add_column_if_missing(bind, "disputes", "priority", "priority VARCHAR(16) DEFAULT 'high'")
    _add_column_if_missing(bind, "disputes", "response_due_at", f"response_due_at {ts_type}")
    _add_column_if_missing(bind, "disputes", "state_version", "state_version INTEGER DEFAULT 0")
    _add_column_if_missing(bind, "disputes", "decision_kind", "decision_kind VARCHAR(64)")
    _add_column_if_missing(
        bind, "disputes", "resolved_by_user_id", "resolved_by_user_id VARCHAR(36)"
    )
    _add_column_if_missing(bind, "disputes", "resolved_at", f"resolved_at {ts_type}")
    _add_column_if_missing(
        bind, "support_tickets", "state_version", "state_version INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind,
        "support_tickets",
        "idempotency_key_hash",
        "idempotency_key_hash VARCHAR(64)",
    )
    _add_column_if_missing(
        bind,
        "support_tickets",
        "request_fingerprint",
        "request_fingerprint VARCHAR(64)",
    )
    _add_column_if_missing(bind, "support_tickets", "closed_at", f"closed_at {ts_type}")
    _add_column_if_missing(
        bind, "support_tickets", "closed_by_user_id", "closed_by_user_id VARCHAR(36)"
    )
    _add_column_if_missing(bind, "support_tickets", "reopened_at", f"reopened_at {ts_type}")
    _add_column_if_missing(
        bind, "support_tickets", "priority", "priority VARCHAR(16) DEFAULT 'normal'"
    )
    _add_column_if_missing(bind, "support_tickets", "urgency_code", "urgency_code VARCHAR(32)")
    _add_column_if_missing(
        bind, "support_tickets", "response_due_at", f"response_due_at {ts_type}"
    )
    _add_column_if_missing(
        bind, "support_tickets", "assigned_to_user_id", "assigned_to_user_id VARCHAR(36)"
    )
    if dialect == "sqlite" and "support_tickets" in inspect(bind).get_table_names():
        with bind.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_support_ticket_author_idempotency "
                    "ON support_tickets(author_user_id, idempotency_key_hash) "
                    "WHERE idempotency_key_hash IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_support_tickets_priority "
                    "ON support_tickets(priority)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_support_tickets_urgency_code "
                    "ON support_tickets(urgency_code)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_support_tickets_response_due_at "
                    "ON support_tickets(response_due_at)"
                )
            )
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_support_tickets_assigned_to_user_id "
                "ON support_tickets(assigned_to_user_id)"
            ))
    if "bookings" in inspect(bind).get_table_names():
        from booker_api.offer_version_binding import backfill_accepted_offer_versions

        with bind.begin() as conn:
            backfill_accepted_offer_versions(conn)
    if dialect == "sqlite" and "money_movements" in inspect(bind).get_table_names():
        _ensure_sqlite_money_movements(bind)
    if dialect == "sqlite" and {
        "offer_versions",
        "payment_obligations",
    } <= set(inspect(bind).get_table_names()):
        _ensure_sqlite_payment_deadline_guards(bind)
    if dialect == "sqlite" and "reconciliation_entries" in inspect(bind).get_table_names():
        _ensure_sqlite_reconciliation_guards(bind)
    if dialect == "sqlite" and "data_subject_request_events" in inspect(bind).get_table_names():
        with bind.begin() as conn:
            for action in ("UPDATE", "DELETE"):
                conn.execute(text(
                    f"CREATE TRIGGER IF NOT EXISTS data_subject_events_no_{action.lower()} "
                    f"BEFORE {action} ON data_subject_request_events "
                    "BEGIN SELECT RAISE(ABORT, 'subject events are immutable'); END"
                ))
    if dialect == "sqlite":
        legal_tables = {"legal_document_versions", "consent_events"}
        present = legal_tables & set(inspect(bind).get_table_names())
        if present:
            if present != legal_tables:
                raise RuntimeError("Incomplete SQLite legal ledger schema")
            _ensure_sqlite_legal_guards(bind)
    if dialect == "sqlite" and {
        "offer_acknowledgements",
        "contract_signatures",
    } <= set(inspect(bind).get_table_names()):
        _ensure_sqlite_attestation_guards(bind)
    if dialect == "sqlite" and "external_payment_events" in inspect(bind).get_table_names():
        _ensure_sqlite_external_event_guards(bind)
    if dialect == "sqlite" and "conversations" in inspect(bind).get_table_names():
        _ensure_sqlite_request_conversations(bind)
        _ensure_sqlite_message_sequences(
            bind, backfill_read_positions=not read_state_has_sequence
        )
        _ensure_sqlite_conversation_read_states(bind)
    if dialect == "sqlite" and "organization_invitations" in inspect(bind).get_table_names():
        _ensure_sqlite_organization_invitations(bind)
    if dialect == "sqlite" and "users" in inspect(bind).get_table_names():
        with bind.begin() as conn:
            # New admin grants require proof; existing legacy admins remain usable.
            conn.execute(text("DROP TRIGGER IF EXISTS users_admin_verified_email"))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS users_admin_verified_email "
                "BEFORE UPDATE OF is_platform_admin, email_verified_at, "
                "email_verification_required_at ON users "
                "WHEN NEW.is_platform_admin = 1 AND NEW.email_verified_at IS NULL "
                "AND (OLD.is_platform_admin = 0 OR NEW.email_verification_required_at IS NOT NULL) "
                "BEGIN SELECT RAISE(ABORT, 'admin email verification required'); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS users_admin_verified_email_insert "
                "BEFORE INSERT ON users "
                "WHEN NEW.is_platform_admin = 1 AND NEW.email_verified_at IS NULL "
                "BEGIN SELECT RAISE(ABORT, 'admin email verification required'); END"
            ))
            conn.execute(text("DROP TRIGGER IF EXISTS users_support_operator_verified_email"))
            conn.execute(text(
                "CREATE TRIGGER users_support_operator_verified_email "
                "BEFORE UPDATE OF is_support_operator, email_verified_at ON users "
                "WHEN NEW.is_support_operator = 1 AND NEW.email_verified_at IS NULL "
                "BEGIN SELECT RAISE(ABORT, 'support operator email verification required'); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS users_support_operator_verified_email_insert "
                "BEFORE INSERT ON users "
                "WHEN NEW.is_support_operator = 1 AND NEW.email_verified_at IS NULL "
                "BEGIN SELECT RAISE(ABORT, 'support operator email verification required'); END"
            ))


def _ensure_sqlite_request_conversations(bind) -> None:
    """Bring create_all-managed pilot SQLite to the request-conversation schema."""
    columns = {column["name"]: column for column in inspect(bind).get_columns("conversations")}
    booking_required = not columns["booking_id"]["nullable"]
    snapshot_optional = any(
        columns[name]["nullable"]
        for name in (
            "customer_org_id",
            "supplier_org_id",
            "customer_name_snapshot",
            "supplier_name_snapshot",
        )
    )
    backfill = (
        "UPDATE conversations SET request_id = ("
        "SELECT o.request_id FROM bookings b JOIN offers o ON o.id = b.offer_id "
        "WHERE b.id = conversations.booking_id) WHERE request_id IS NULL"
    )
    participant_backfill = (
        "UPDATE conversations SET "
        "customer_org_id = COALESCE(customer_org_id, ("
        "SELECT e.organization_id FROM requests r JOIN events e ON e.id = r.event_id "
        "WHERE r.id = conversations.request_id)), "
        "supplier_org_id = COALESCE(supplier_org_id, ("
        "SELECT r.supplier_org_id FROM requests r "
        "WHERE r.id = conversations.request_id))"
    )
    participant_name_backfill = (
        "UPDATE conversations SET "
        "customer_name_snapshot = COALESCE(customer_name_snapshot, ("
        "SELECT o.name FROM organizations o WHERE o.id = customer_org_id)), "
        "supplier_name_snapshot = COALESCE(supplier_name_snapshot, ("
        "SELECT o.name FROM organizations o WHERE o.id = supplier_org_id))"
    )
    if booking_required or snapshot_optional:
        raw = bind.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(backfill)
            cursor.execute(participant_backfill)
            cursor.execute(participant_name_backfill)
            cursor.execute(
                "CREATE TABLE conversations_new ("
                "id VARCHAR(36) PRIMARY KEY NOT NULL, "
                "request_id VARCHAR(36) REFERENCES requests(id), "
                "booking_id VARCHAR(36) REFERENCES bookings(id), "
                "customer_org_id VARCHAR(36) NOT NULL REFERENCES organizations(id), "
                "supplier_org_id VARCHAR(36) NOT NULL REFERENCES organizations(id), "
                "customer_name_snapshot VARCHAR(255) NOT NULL, "
                "supplier_name_snapshot VARCHAR(255) NOT NULL, "
                "next_message_sequence INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE(request_id), UNIQUE(booking_id))"
            )
            cursor.execute(
                "INSERT INTO conversations_new "
                "(id, request_id, booking_id, customer_org_id, supplier_org_id, "
                "customer_name_snapshot, supplier_name_snapshot, next_message_sequence) "
                "SELECT id, request_id, booking_id, customer_org_id, supplier_org_id, "
                "customer_name_snapshot, supplier_name_snapshot, next_message_sequence "
                "FROM conversations"
            )
            cursor.execute("DROP TABLE conversations")
            cursor.execute("ALTER TABLE conversations_new RENAME TO conversations")
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_request_id "
                "ON conversations(request_id) WHERE request_id IS NOT NULL"
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_message_conversation_idempotency "
                "ON messages(conversation_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
            raw.commit()
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return
    with bind.begin() as conn:
        conn.execute(text(backfill))
        conn.execute(text(participant_backfill))
        conn.execute(text(participant_name_backfill))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_request_id "
                "ON conversations(request_id) WHERE request_id IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_message_conversation_idempotency "
                "ON messages(conversation_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
        )


def _ensure_sqlite_message_sequences(bind, *, backfill_read_positions: bool) -> None:
    """Adopt legacy runtime databases into monotonic unread positions."""
    with bind.begin() as conn:
        conn.execute(
            text(
                "WITH ranked AS (SELECT id, ROW_NUMBER() OVER (PARTITION BY conversation_id "
                "ORDER BY created_at, id) AS seq FROM messages) "
                "UPDATE messages SET sequence = (SELECT ranked.seq FROM ranked "
                "WHERE ranked.id = messages.id) WHERE sequence IS NULL"
            )
        )
        conn.execute(
            text(
                "UPDATE conversations SET next_message_sequence = COALESCE(("
                "SELECT MAX(messages.sequence) + 1 FROM messages "
                "WHERE messages.conversation_id = conversations.id), 1)"
            )
        )
        if backfill_read_positions:
            conn.execute(
                text(
                    "UPDATE conversation_read_states SET last_read_sequence = COALESCE(("
                    "SELECT MAX(messages.sequence) FROM messages "
                    "WHERE messages.conversation_id = conversation_read_states.conversation_id "
                    "AND messages.created_at <= conversation_read_states.read_at), 0)"
                )
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_conversation_sequence "
                "ON messages(conversation_id, sequence)"
            )
        )


def _ensure_sqlite_conversation_read_states(bind) -> None:
    """Scope read positions to one immutable conversation participant organization."""
    inspector = inspect(bind)
    if "conversation_read_states" not in inspector.get_table_names():
        return
    column_details = {
        column["name"]: column
        for column in inspector.get_columns("conversation_read_states")
    }
    columns = set(column_details)
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("conversation_read_states")
    }
    expected = ("conversation_id", "user_id", "organization_id")
    if (
        "organization_id" in columns
        and not column_details["organization_id"]["nullable"]
        and expected in unique_sets
        and ("conversation_id", "user_id") not in unique_sets
    ):
        return

    if "organization_id" in columns:
        copy_sql = (
            "INSERT INTO conversation_read_states_new "
            "(id, conversation_id, user_id, organization_id, last_read_sequence, read_at) "
            "SELECT rs.id, rs.conversation_id, rs.user_id, rs.organization_id, "
            "rs.last_read_sequence, rs.read_at FROM conversation_read_states rs "
            "JOIN conversations c ON c.id = rs.conversation_id "
            "JOIN team_members tm ON tm.user_id = rs.user_id "
            "AND tm.organization_id = rs.organization_id "
            "WHERE rs.organization_id IN (c.customer_org_id, c.supplier_org_id)"
        )
    else:
        copy_sql = (
            "INSERT INTO conversation_read_states_new "
            "(id, conversation_id, user_id, organization_id, last_read_sequence, read_at) "
            "SELECT rs.id, rs.conversation_id, rs.user_id, MIN(tm.organization_id), "
            "rs.last_read_sequence, rs.read_at FROM conversation_read_states rs "
            "JOIN conversations c ON c.id = rs.conversation_id "
            "JOIN team_members tm ON tm.user_id = rs.user_id "
            "AND tm.organization_id IN (c.customer_org_id, c.supplier_org_id) "
            "GROUP BY rs.id, rs.conversation_id, rs.user_id, "
            "rs.last_read_sequence, rs.read_at "
            "HAVING COUNT(DISTINCT tm.organization_id) = 1"
        )

    raw = bind.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "CREATE TABLE conversation_read_states_new ("
            "id VARCHAR(36) PRIMARY KEY NOT NULL, "
            "conversation_id VARCHAR(36) NOT NULL REFERENCES conversations(id), "
            "user_id VARCHAR(36) NOT NULL REFERENCES users(id), "
            "organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id), "
            "last_read_sequence INTEGER NOT NULL DEFAULT 0, "
            "read_at DATETIME NOT NULL, "
            "CONSTRAINT uq_conversation_read_state_party "
            "UNIQUE (conversation_id, user_id, organization_id))"
        )
        cursor.execute(copy_sql)
        cursor.execute("DROP TABLE conversation_read_states")
        cursor.execute(
            "ALTER TABLE conversation_read_states_new RENAME TO conversation_read_states"
        )
        cursor.execute(
            "CREATE INDEX ix_conversation_read_states_conversation_id "
            "ON conversation_read_states(conversation_id)"
        )
        cursor.execute(
            "CREATE INDEX ix_conversation_read_states_user_id "
            "ON conversation_read_states(user_id)"
        )
        cursor.execute(
            "CREATE INDEX ix_conversation_read_states_organization_id "
            "ON conversation_read_states(organization_id)"
        )
        violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"conversation read-state foreign key violations: {violations}")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
        raw.close()


def _ensure_sqlite_organization_invitations(bind) -> None:
    """Replace legacy global invitation idempotency with the actor-scoped invariant."""
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("organization_invitations")}
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("organization_invitations")
    }
    expected = ("organization_id", "invited_by_user_id", "idempotency_key")
    if "idempotency_key" in columns and expected in unique_sets and ("idempotency_key",) not in unique_sets:
        return

    idem_expr = "idempotency_key" if "idempotency_key" in columns else "'legacy-' || id"
    raw = bind.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "CREATE TABLE organization_invitations_new ("
            "id VARCHAR(36) PRIMARY KEY NOT NULL, "
            "organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id), "
            "email VARCHAR(255) NOT NULL, "
            "invited_user_id VARCHAR(36) REFERENCES users(id), "
            "role VARCHAR(32) NOT NULL, "
            "can_confirm_offer BOOLEAN NOT NULL, "
            "token_hash VARCHAR(64) NOT NULL UNIQUE, "
            "idempotency_key VARCHAR(64) NOT NULL, "
            "status VARCHAR(16) NOT NULL, "
            "invited_by_user_id VARCHAR(36) NOT NULL REFERENCES users(id), "
            "expires_at DATETIME NOT NULL, accepted_at DATETIME, revoked_at DATETIME, "
            "created_at DATETIME NOT NULL, "
            "CONSTRAINT uq_organization_invitation_actor_idempotency "
            "UNIQUE (organization_id, invited_by_user_id, idempotency_key))"
        )
        cursor.execute(
            "INSERT INTO organization_invitations_new "
            "(id, organization_id, email, invited_user_id, role, can_confirm_offer, token_hash, "
            "idempotency_key, status, invited_by_user_id, expires_at, accepted_at, revoked_at, "
            "created_at) SELECT id, organization_id, email, invited_user_id, role, "
            f"can_confirm_offer, token_hash, {idem_expr}, status, invited_by_user_id, expires_at, "
            "accepted_at, revoked_at, created_at FROM organization_invitations"
        )
        cursor.execute("DROP TABLE organization_invitations")
        cursor.execute(
            "ALTER TABLE organization_invitations_new RENAME TO organization_invitations"
        )
        cursor.execute(
            "CREATE INDEX ix_organization_invitations_organization_id "
            "ON organization_invitations(organization_id)"
        )
        cursor.execute(
            "CREATE INDEX ix_organization_invitations_email ON organization_invitations(email)"
        )
        cursor.execute(
            "CREATE INDEX ix_organization_invitations_status ON organization_invitations(status)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX uq_organization_invitation_pending_email "
            "ON organization_invitations(organization_id, email) WHERE status = 'pending'"
        )
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _ensure_sqlite_money_movements(bind) -> None:
    """Backfill truthful historical rows and install DB-level append-only guards."""
    with bind.begin() as conn:
        conn.execute(
            text(
                "UPDATE payments SET status = 'external_recorded' "
                "WHERE provider = 'external' AND status = 'succeeded'"
            )
        )
        conn.execute(text(
            "UPDATE bookings SET payout_blocked = 1, "
            "payout_block_reason = 'legacy_external_unverified' "
            "WHERE status IN ('Confirmed', 'InProgress') AND id IN "
            "(SELECT booking_id FROM payments WHERE provider = 'external' "
            "AND status = 'external_recorded') AND payout_blocked = 0"
        ))
        rows = conn.execute(
            text(
                "SELECT p.id, p.booking_id, p.obligation_id, p.amount_rub, p.provider, p.status "
                "FROM payments p LEFT JOIN money_movements m "
                "ON m.payment_id = p.id AND m.kind = 'capture' "
                "WHERE p.provider <> 'external' "
                "AND p.status IN ('succeeded', 'refunded', 'partially_refunded') "
                "AND m.id IS NULL"
            )
        ).mappings()
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO money_movements "
                    "(id, booking_id, payment_id, obligation_id, kind, direction, amount_rub, "
                    "currency, provider, source_type, source_id, metadata_json, created_at) "
                    "VALUES (:id, :booking_id, :payment_id, :obligation_id, 'capture', 'credit', "
                    ":amount, 'RUB', :provider, 'runtime-backfill', :source_id, "
                    "'{\"backfill\":true}', CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "booking_id": row["booking_id"],
                    "payment_id": row["id"],
                    "obligation_id": row["obligation_id"],
                    "amount": row["amount_rub"],
                    "provider": row["provider"],
                    "source_id": row["id"],
                },
            )
            refund_amount = 0
            if row["status"] == "refunded":
                refund_amount = row["amount_rub"]
            elif row["status"] == "partially_refunded":
                refund_amount = conn.execute(
                    text(
                        "SELECT COALESCE(SUM(amount_rub), 0) FROM refund_requests "
                        "WHERE payment_id = :payment_id AND status = 'refunded'"
                    ),
                    {"payment_id": row["id"]},
                ).scalar_one()
                if refund_amount <= 0 or refund_amount >= row["amount_rub"]:
                    raise RuntimeError(
                        "Cannot backfill partially_refunded payment without a verified partial "
                        f"amount: {row['id']}"
                    )
            if refund_amount:
                conn.execute(
                    text(
                        "INSERT INTO money_movements "
                        "(id, booking_id, payment_id, obligation_id, kind, direction, amount_rub, "
                        "currency, provider, source_type, source_id, metadata_json, created_at) "
                        "VALUES (:id, :booking_id, :payment_id, :obligation_id, 'refund', 'debit', "
                        ":amount, 'RUB', :provider, 'runtime-backfill-refund', :source_id, "
                        "'{\"backfill\":true}', CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": str(uuid4()),
                        "booking_id": row["booking_id"],
                        "payment_id": row["id"],
                        "obligation_id": row["obligation_id"],
                        "amount": refund_amount,
                        "provider": row["provider"],
                        "source_id": row["id"],
                    },
                )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS money_movements_no_update "
                "BEFORE UPDATE ON money_movements "
                "BEGIN SELECT RAISE(ABORT, 'money_movements is append-only'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS money_movements_no_delete "
                "BEFORE DELETE ON money_movements "
                "BEGIN SELECT RAISE(ABORT, 'money_movements is append-only'); END"
            )
        )


def _ensure_sqlite_attestation_guards(bind) -> None:
    """Keep offer acknowledgements and contract signatures append-only."""
    with bind.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS contracts_snapshot_immutable "
            "BEFORE UPDATE ON contracts WHEN NEW.body IS NOT OLD.body "
            "OR NEW.offer_version_id IS NOT OLD.offer_version_id "
            "OR NEW.body_sha256 IS NOT OLD.body_sha256 OR NEW.effect IS NOT OLD.effect "
            "OR NEW.template_key IS NOT OLD.template_key "
            "OR NEW.legal_pack_version IS NOT OLD.legal_pack_version "
            "BEGIN SELECT RAISE(ABORT, 'contract snapshot is immutable'); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS contracts_no_delete BEFORE DELETE ON contracts "
            "BEGIN SELECT RAISE(ABORT, 'contract snapshot is immutable'); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS contract_challenges_update_guard "
            "BEFORE UPDATE ON contract_challenges WHEN NEW.id IS NOT OLD.id "
            "OR NEW.contract_id IS NOT OLD.contract_id OR NEW.side IS NOT OLD.side "
            "OR NEW.actor_user_id IS NOT OLD.actor_user_id OR NEW.otp_hash IS NOT OLD.otp_hash "
            "OR NEW.expires_at IS NOT OLD.expires_at "
            "OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'contract challenge is immutable'); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS contract_challenges_no_delete "
            "BEFORE DELETE ON contract_challenges "
            "BEGIN SELECT RAISE(ABORT, 'contract challenge is immutable'); END"
        ))
        for table in ("contracts", "contract_signatures"):
            conn.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS {table}_offer_version_fk_insert "
                f"BEFORE INSERT ON {table} WHEN NEW.offer_version_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM offer_versions WHERE id = NEW.offer_version_id) "
                "BEGIN SELECT RAISE(ABORT, 'offer version does not exist'); END"
            ))
            conn.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS {table}_offer_version_fk_update "
                f"BEFORE UPDATE OF offer_version_id ON {table} "
                "WHEN NEW.offer_version_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM offer_versions WHERE id = NEW.offer_version_id) "
                "BEGIN SELECT RAISE(ABORT, 'offer version does not exist'); END"
            ))
        for table in ("offer_acknowledgements", "contract_signatures"):
            for action in ("UPDATE", "DELETE"):
                conn.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} "
                        f"BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, "
                        f"'{table} is append-only'); END"
                    )
                )


def _ensure_sqlite_external_event_guards(bind) -> None:
    """Keep external transfer history append-only in create_all-managed SQLite."""
    with bind.begin() as conn:
        for action in ("UPDATE", "DELETE"):
            conn.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS external_payment_events_no_{action.lower()} "
                f"BEFORE {action} ON external_payment_events "
                "BEGIN SELECT RAISE(ABORT, 'external payment event is append-only'); END"
            ))


def _ensure_sqlite_payment_deadline_guards(bind) -> None:
    """Protect accepted schedule terms while allowing payment status updates."""
    with bind.begin() as conn:
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS offer_versions_payment_terms_immutable "
                "BEFORE UPDATE OF payment_terms_json ON offer_versions "
                "BEGIN SELECT RAISE(ABORT, 'offer payment terms are immutable'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS payment_obligations_deadlines_immutable "
                "BEFORE UPDATE OF due_at, grace_until, required_before_check_in "
                "ON payment_obligations "
                "BEGIN SELECT RAISE(ABORT, 'payment deadlines are immutable'); END"
            )
        )


def _ensure_sqlite_reconciliation_guards(bind) -> None:
    with bind.begin() as conn:
        for action in ("UPDATE", "DELETE"):
            conn.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS reconciliation_entries_no_{action.lower()} "
                    f"BEFORE {action} ON reconciliation_entries "
                    "BEGIN SELECT RAISE(ABORT, 'reconciliation entries are immutable'); END"
                )
            )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_identity_immutable "
                "BEFORE UPDATE OF provider, merchant, report_id, content_sha256, period_start, "
                "period_end, received_at ON reconciliation_runs "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation run identity is immutable'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_identity_immutable "
                "BEFORE UPDATE OF run_id, fingerprint, kind, booking_id, payment_id, movement_id, "
                "entry_id, details_json, created_at ON reconciliation_discrepancies "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancy identity is immutable'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_no_delete "
                "BEFORE DELETE ON reconciliation_runs "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation runs are immutable audit'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_no_delete "
                "BEFORE DELETE ON reconciliation_discrepancies "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancies are immutable audit'); END"
            )
        )


def _ensure_sqlite_legal_guards(bind) -> None:
    """Install the migration's legal ledger guards on create_all-managed SQLite."""
    statements = {
        "legal_documents_insert_guard": """
            CREATE TRIGGER IF NOT EXISTS legal_documents_insert_guard
            BEFORE INSERT ON legal_document_versions
            WHEN length(trim(NEW.key)) = 0 OR length(trim(NEW.version)) = 0
              OR length(NEW.content_hash) != 64 OR length(trim(NEW.source_path)) = 0
              OR (NEW.status = 'draft' AND
                  (NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL))
              OR (NEW.status = 'published' AND
                  (NEW.published_at IS NULL OR NEW.retired_at IS NOT NULL))
              OR (NEW.status = 'retired' AND
                  (NEW.published_at IS NULL OR NEW.retired_at IS NULL))
            BEGIN SELECT RAISE(ABORT, 'invalid legal document version'); END
        """,
        "legal_documents_no_delete": """
            CREATE TRIGGER IF NOT EXISTS legal_documents_no_delete
            BEFORE DELETE ON legal_document_versions
            BEGIN SELECT RAISE(ABORT, 'legal document versions are immutable'); END
        """,
        "legal_documents_update_guard": """
            CREATE TRIGGER IF NOT EXISTS legal_documents_update_guard
            BEFORE UPDATE ON legal_document_versions
            WHEN NEW.id IS NOT OLD.id
              OR NEW.key IS NOT OLD.key
              OR NEW.version IS NOT OLD.version
              OR NEW.created_at IS NOT OLD.created_at
              OR NEW.created_by_user_id IS NOT OLD.created_by_user_id
              OR (OLD.status = 'draft' AND (
                    NEW.status NOT IN ('draft', 'published')
                    OR (NEW.status = 'draft' AND
                        (NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL))
                    OR (NEW.status = 'published' AND
                        (NEW.published_at IS NULL OR NEW.retired_at IS NOT NULL
                         OR NEW.content_hash IS NULL OR length(NEW.content_hash) != 64
                         OR length(trim(NEW.source_path)) = 0))))
              OR (OLD.status = 'published' AND (
                    NEW.status NOT IN ('published', 'retired')
                    OR NEW.content_hash IS NOT OLD.content_hash
                    OR NEW.source_path IS NOT OLD.source_path
                    OR NEW.published_at IS NOT OLD.published_at
                    OR (NEW.status = 'published' AND NEW.retired_at IS NOT NULL)
                    OR (NEW.status = 'retired' AND NEW.retired_at IS NULL)))
              OR (OLD.status = 'retired' AND (
                    NEW.status IS NOT OLD.status
                    OR NEW.content_hash IS NOT OLD.content_hash
                    OR NEW.source_path IS NOT OLD.source_path
                    OR NEW.published_at IS NOT OLD.published_at
                    OR NEW.retired_at IS NOT OLD.retired_at))
            BEGIN SELECT RAISE(ABORT, 'legal document version is immutable'); END
        """,
        "consent_events_insert_guard": """
            CREATE TRIGGER IF NOT EXISTS consent_events_insert_guard
            BEFORE INSERT ON consent_events
            WHEN NEW.action NOT IN ('accepted', 'withdrawn')
              OR NEW.kind NOT IN ('offer', 'privacy', 'processing', 'marketing_email')
              OR length(trim(NEW.document_version)) = 0
              OR length(NEW.document_hash) != 64
            BEGIN SELECT RAISE(ABORT, 'invalid consent event'); END
        """,
        "consent_events_no_update": (
            "CREATE TRIGGER IF NOT EXISTS consent_events_no_update "
            "BEFORE UPDATE ON consent_events "
            "BEGIN SELECT RAISE(ABORT, 'consent events are append-only'); END"
        ),
        "consent_events_no_delete": (
            "CREATE TRIGGER IF NOT EXISTS consent_events_no_delete "
            "BEFORE DELETE ON consent_events "
            "BEGIN SELECT RAISE(ABORT, 'consent events are append-only'); END"
        ),
    }
    with bind.begin() as conn:
        index_sql = (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_document_published_key "
            "ON legal_document_versions(key) WHERE status = 'published'"
        )
        conn.execute(text(index_sql))
        for statement in statements.values():
            conn.execute(text(statement))
        installed = dict(conn.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
            "AND name IN ('legal_documents_insert_guard', 'legal_documents_no_delete', "
            "'legal_documents_update_guard', 'consent_events_insert_guard', "
            "'consent_events_no_update', 'consent_events_no_delete')"
        )).all())
        for name, statement in statements.items():
            expected = " ".join(statement.split()).replace(
                "CREATE TRIGGER IF NOT EXISTS ", "CREATE TRIGGER ", 1
            ).rstrip(";")
            actual = " ".join((installed.get(name) or "").split()).rstrip(";")
            if actual != expected:
                raise RuntimeError(f"SQLite legal ledger guard mismatch: {name}")
        index_actual = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type = 'index' "
            "AND name = 'uq_legal_document_published_key'"
        )).scalar_one_or_none()
        index_expected = index_sql.replace("INDEX IF NOT EXISTS ", "INDEX ")
        def normalized_index_sql(value: str) -> str:
            return " ".join(value.replace('"key"', "key").replace(" (", "(").split())

        if normalized_index_sql(index_actual or "") != normalized_index_sql(index_expected):
            raise RuntimeError("SQLite legal ledger published-key guard mismatch")


def ensure_sqlite_columns(bind) -> None:
    ensure_missing_columns(bind)


def make_engine(url: str | None = None):
    db_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return enable_sqlite_foreign_keys(
        create_engine(db_url, connect_args=connect_args, future=True)
    )


def run_migrations(url: str | None = None) -> None:
    """Apply Alembic revisions (Postgres prod path)."""
    from alembic.config import Config

    from alembic import command

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini))
    # ConfigParser treats % as interpolation; preserve URL-encoded credentials.
    cfg.set_main_option("sqlalchemy.url", (url or settings.database_url).replace("%", "%%"))
    command.upgrade(cfg, "head")


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema(bind=None) -> None:
    target = bind or engine
    if target.dialect.name == "postgresql":
        run_migrations(target.url.render_as_string(hide_password=False))
        return
    Base.metadata.create_all(bind=target)
    ensure_missing_columns(target)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
