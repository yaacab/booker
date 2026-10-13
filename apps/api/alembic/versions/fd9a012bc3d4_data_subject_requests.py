"""Add subject requests, append-only events and user legal holds.

Revision ID: fd9a012bc3d4
Revises: fc8f901ab2c3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fd9a012bc3d4"
down_revision: str | None = "fc8f901ab2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "optional_processing_restricted" not in user_columns:
        op.add_column("users", sa.Column("optional_processing_restricted", sa.Boolean(),
                                         nullable=False, server_default=sa.false()))
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if {"data_subject_requests", "data_subject_request_events", "legal_holds"} <= existing:
        # Only the SQLite runtime creates tables ahead of Alembic. Refuse a
        # partial or unexpected PostgreSQL schema instead of stamping it.
        if op.get_bind().dialect.name != "sqlite":
            raise RuntimeError("Existing subject tables require a reviewed PostgreSQL adoption")
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("legal_holds")}
        if "uq_legal_holds_active_subject" not in indexes:
            raise RuntimeError("Existing legal holds lack the active-subject guard")
        triggers = {row[0] for row in op.get_bind().execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='data_subject_request_events'"
        ))}
        if {"data_subject_events_no_update", "data_subject_events_no_delete"} - triggers:
            raise RuntimeError("Existing subject events lack immutable guards")
        return
    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_type", sa.String(16), nullable=False),
        sa.Column("correction_field", sa.String(32), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_reason_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("subject_user_id", "idempotency_key_hash", name="uq_subject_request_idempotency"),
        sa.CheckConstraint("request_type IN ('access','export','restrict','delete','correct')", name="ck_subject_request_type"),
        sa.CheckConstraint("status IN ('pending','in_review','needs_info','approved','rejected','completed','cancelled')",
                           name="ck_subject_request_status"),
    )
    op.create_index("ix_data_subject_requests_subject_user_id", "data_subject_requests", ["subject_user_id"])
    op.create_index("ix_data_subject_requests_request_type", "data_subject_requests", ["request_type"])
    op.create_index("ix_data_subject_requests_status", "data_subject_requests", ["status"])
    op.create_table(
        "data_subject_request_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("data_subject_requests.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "state_version", name="uq_subject_event_version"),
    )
    op.create_index("ix_data_subject_request_events_request_id", "data_subject_request_events", ["request_id"])
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope = 'user'", name="ck_legal_hold_scope"),
    )
    op.create_index("ix_legal_holds_subject_user_id", "legal_holds", ["subject_user_id"])
    op.create_index("uq_legal_holds_active_subject", "legal_holds", ["subject_user_id"], unique=True,
                    sqlite_where=sa.text("released_at IS NULL"),
                    postgresql_where=sa.text("released_at IS NULL"))
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER data_subject_events_no_update BEFORE UPDATE ON data_subject_request_events "
                   "BEGIN SELECT RAISE(ABORT, 'subject events are immutable'); END")
        op.execute("CREATE TRIGGER data_subject_events_no_delete BEFORE DELETE ON data_subject_request_events "
                   "BEGIN SELECT RAISE(ABORT, 'subject events are immutable'); END")
    else:
        op.execute("CREATE FUNCTION booker_subject_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ "
                   "BEGIN RAISE EXCEPTION 'subject events are immutable'; END; $$")
        op.execute("CREATE TRIGGER data_subject_events_no_mutation BEFORE UPDATE OR DELETE "
                   "ON data_subject_request_events FOR EACH ROW EXECUTE FUNCTION booker_subject_events_immutable()")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS data_subject_events_no_delete")
        op.execute("DROP TRIGGER IF EXISTS data_subject_events_no_update")
    else:
        op.execute("DROP TRIGGER IF EXISTS data_subject_events_no_mutation ON data_subject_request_events")
        op.execute("DROP FUNCTION IF EXISTS booker_subject_events_immutable()")
    op.drop_index("uq_legal_holds_active_subject", table_name="legal_holds")
    op.drop_index("ix_legal_holds_subject_user_id", table_name="legal_holds")
    op.drop_table("legal_holds")
    op.drop_index("ix_data_subject_request_events_request_id", table_name="data_subject_request_events")
    op.drop_table("data_subject_request_events")
    op.drop_index("ix_data_subject_requests_status", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_request_type", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_subject_user_id", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
    op.drop_column("users", "optional_processing_restricted")
