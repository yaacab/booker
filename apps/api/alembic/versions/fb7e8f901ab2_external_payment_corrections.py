"""Append-only external payment evidence and correction decisions.

Revision ID: fb7e8f901ab2
Revises: fa6d7e8f901b
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fb7e8f901ab2"
down_revision: str | None = "fa6d7e8f901b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    payment_columns = {column["name"] for column in inspector.get_columns("payments")}
    if "external_evidence_version" not in payment_columns:
        op.add_column("payments", sa.Column("external_evidence_version", sa.Integer(),
                                            nullable=False, server_default="0"))
    if "external_payment_events" not in inspector.get_table_names():
        op.create_table(
        "external_payment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("external_payment_reports.id"), nullable=False),
        sa.Column("parent_event_id", sa.String(36), sa.ForeignKey("external_payment_events.id")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("external_payment_events")}
    if "ix_external_payment_events_payment_id" not in indexes:
        op.create_index("ix_external_payment_events_payment_id", "external_payment_events", ["payment_id"])
    if "ix_external_payment_events_report_id" not in indexes:
        op.create_index("ix_external_payment_events_report_id", "external_payment_events", ["report_id"])
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER IF NOT EXISTS external_payment_events_no_update BEFORE UPDATE ON "
                   "external_payment_events BEGIN SELECT RAISE(ABORT, 'append-only'); END")
        op.execute("CREATE TRIGGER IF NOT EXISTS external_payment_events_no_delete BEFORE DELETE ON "
                   "external_payment_events BEGIN SELECT RAISE(ABORT, 'append-only'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_external_payment_event_mutation() RETURNS trigger AS $$ "
                   "BEGIN RAISE EXCEPTION 'append-only'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER external_payment_events_no_update BEFORE UPDATE ON "
                   "external_payment_events FOR EACH ROW EXECUTE FUNCTION "
                   "reject_external_payment_event_mutation()")
        op.execute("CREATE TRIGGER external_payment_events_no_delete BEFORE DELETE ON "
                   "external_payment_events FOR EACH ROW EXECUTE FUNCTION "
                   "reject_external_payment_event_mutation()")
    # Historical external captures could have set Confirmed without a bank fact.
    # Keep their lifecycle history, but quarantine new check-in and payouts.
    op.execute(sa.text(
        "UPDATE bookings SET payout_blocked = TRUE, "
        "payout_block_reason = 'legacy_external_unverified' "
        "WHERE status IN ('Confirmed', 'InProgress') AND id IN "
        "(SELECT booking_id FROM payments WHERE provider = 'external' "
        "AND status = 'external_recorded') AND payout_blocked = FALSE"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM external_payment_events")).scalar_one():
        raise RuntimeError("Refusing to drop non-empty external payment event history")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS external_payment_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS external_payment_events_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS external_payment_events_no_update ON external_payment_events")
        op.execute("DROP TRIGGER IF EXISTS external_payment_events_no_delete ON external_payment_events")
        op.execute("DROP FUNCTION IF EXISTS reject_external_payment_event_mutation()")
    op.drop_index("ix_external_payment_events_report_id", table_name="external_payment_events")
    op.drop_index("ix_external_payment_events_payment_id", table_name="external_payment_events")
    op.drop_table("external_payment_events")
    op.drop_column("payments", "external_evidence_version")
