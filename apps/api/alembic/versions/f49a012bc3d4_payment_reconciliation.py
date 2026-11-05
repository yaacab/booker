"""Add provider report reconciliation and payout blocks.

Revision ID: f49a012bc3d4
Revises: f38f901ab2c3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f49a012bc3d4"
down_revision: str | None = "f38f901ab2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    payment_columns = {row["name"] for row in inspector.get_columns("payments")}
    if "provider_reference" not in payment_columns:
        op.add_column("payments", sa.Column("provider_reference", sa.String(128), nullable=True))
    if "provider_merchant" not in payment_columns:
        op.add_column(
            "payments",
            sa.Column("provider_merchant", sa.String(128), nullable=False, server_default=""),
        )
    payment_indexes = {row["name"] for row in sa.inspect(bind).get_indexes("payments")}
    if "uq_payments_provider_reference" not in payment_indexes:
        op.create_index(
            "uq_payments_provider_reference",
            "payments",
            ["provider", "provider_merchant", "provider_reference"],
            unique=True,
            sqlite_where=sa.text("provider_reference IS NOT NULL"),
            postgresql_where=sa.text("provider_reference IS NOT NULL"),
        )
    booking_columns = {row["name"] for row in inspector.get_columns("bookings")}
    if "payout_blocked" not in booking_columns:
        op.add_column(
            "bookings",
            sa.Column("payout_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "payout_block_reason" not in booking_columns:
        op.add_column(
            "bookings",
            sa.Column("payout_block_reason", sa.String(64), nullable=False, server_default=""),
        )
    reconciliation_tables = {
        "reconciliation_runs",
        "reconciliation_entries",
        "reconciliation_discrepancies",
    }
    present_reconciliation_tables = reconciliation_tables & set(inspector.get_table_names())
    if present_reconciliation_tables and present_reconciliation_tables != reconciliation_tables:
        raise RuntimeError("Partial reconciliation schema requires operator repair")
    if present_reconciliation_tables == reconciliation_tables:
        if bind.dialect.name != "sqlite":
            raise RuntimeError(
                "Pre-existing PostgreSQL reconciliation schema requires trigger verification"
            )
        if bind.dialect.name == "sqlite":
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_entries_no_update "
                "BEFORE UPDATE ON reconciliation_entries "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation entries are immutable'); END"
            )
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_entries_no_delete "
                "BEFORE DELETE ON reconciliation_entries "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation entries are immutable'); END"
            )
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_identity_immutable "
                "BEFORE UPDATE OF provider, merchant, report_id, content_sha256, period_start, "
                "period_end, received_at ON reconciliation_runs "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation run identity is immutable'); END"
            )
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_identity_immutable "
                "BEFORE UPDATE OF run_id, fingerprint, kind, booking_id, payment_id, movement_id, "
                "entry_id, details_json, created_at ON reconciliation_discrepancies "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancy identity is immutable'); END"
            )
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_no_delete "
                "BEFORE DELETE ON reconciliation_runs "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation runs are immutable audit'); END"
            )
            op.execute(
                "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_no_delete "
                "BEFORE DELETE ON reconciliation_discrepancies "
                "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancies are immutable audit'); END"
            )
        return
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("merchant", sa.String(128), nullable=False),
        sa.Column("report_id", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "merchant", "report_id"),
        sa.UniqueConstraint("provider", "merchant", "content_sha256"),
    )
    op.create_index("ix_reconciliation_runs_provider", "reconciliation_runs", ["provider"])
    op.create_table(
        "reconciliation_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("reconciliation_runs.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("merchant", sa.String(128), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("provider_operation_id", sa.String(128), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("operation_kind", sa.String(32), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("provider_status", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "line_no"),
        sa.UniqueConstraint(
            "provider",
            "merchant",
            "provider_operation_id",
            name="uq_reconciliation_provider_operation",
        ),
    )
    op.create_index("ix_reconciliation_entries_run_id", "reconciliation_entries", ["run_id"])
    op.create_index(
        "ix_reconciliation_entries_provider_operation_id",
        "reconciliation_entries",
        ["provider_operation_id"],
    )
    op.create_index(
        "ix_reconciliation_entries_provider_reference",
        "reconciliation_entries",
        ["provider_reference"],
    )
    op.create_table(
        "reconciliation_discrepancies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("reconciliation_runs.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("booking_id", sa.String(36), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("movement_id", sa.String(36), sa.ForeignKey("money_movements.id"), nullable=True),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("reconciliation_entries.id"), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "fingerprint"),
    )
    op.create_index(
        "ix_reconciliation_discrepancies_run_id", "reconciliation_discrepancies", ["run_id"]
    )
    op.create_index(
        "ix_reconciliation_discrepancies_kind", "reconciliation_discrepancies", ["kind"]
    )
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_entries_no_update "
            "BEFORE UPDATE ON reconciliation_entries "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation entries are immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_entries_no_delete "
            "BEFORE DELETE ON reconciliation_entries "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation entries are immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_identity_immutable "
            "BEFORE UPDATE OF provider, merchant, report_id, content_sha256, period_start, "
            "period_end, received_at ON reconciliation_runs "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation run identity is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_identity_immutable "
            "BEFORE UPDATE OF run_id, fingerprint, kind, booking_id, payment_id, movement_id, "
            "entry_id, details_json, created_at ON reconciliation_discrepancies "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancy identity is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_runs_no_delete "
            "BEFORE DELETE ON reconciliation_runs "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation runs are immutable audit'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS reconciliation_discrepancies_no_delete "
            "BEFORE DELETE ON reconciliation_discrepancies "
            "BEGIN SELECT RAISE(ABORT, 'reconciliation discrepancies are immutable audit'); END"
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_reconciliation_entry_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'reconciliation entries are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER reconciliation_entries_immutable BEFORE UPDATE OR DELETE "
            "ON reconciliation_entries FOR EACH ROW "
            "EXECUTE FUNCTION reject_reconciliation_entry_mutation()"
        )
        op.execute(
            """
            CREATE FUNCTION reject_reconciliation_run_identity_mutation() RETURNS trigger AS $$
            BEGIN
              IF NEW.provider IS DISTINCT FROM OLD.provider
                 OR NEW.merchant IS DISTINCT FROM OLD.merchant
                 OR NEW.report_id IS DISTINCT FROM OLD.report_id
                 OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
                 OR NEW.period_start IS DISTINCT FROM OLD.period_start
                 OR NEW.period_end IS DISTINCT FROM OLD.period_end
                 OR NEW.received_at IS DISTINCT FROM OLD.received_at THEN
                RAISE EXCEPTION 'reconciliation run identity is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER reconciliation_runs_identity_immutable BEFORE UPDATE "
            "ON reconciliation_runs FOR EACH ROW "
            "EXECUTE FUNCTION reject_reconciliation_run_identity_mutation()"
        )
        op.execute(
            """
            CREATE FUNCTION reject_reconciliation_discrepancy_identity_mutation() RETURNS trigger AS $$
            BEGIN
              IF NEW.run_id IS DISTINCT FROM OLD.run_id
                 OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
                 OR NEW.kind IS DISTINCT FROM OLD.kind
                 OR NEW.booking_id IS DISTINCT FROM OLD.booking_id
                 OR NEW.payment_id IS DISTINCT FROM OLD.payment_id
                 OR NEW.movement_id IS DISTINCT FROM OLD.movement_id
                 OR NEW.entry_id IS DISTINCT FROM OLD.entry_id
                 OR NEW.details_json IS DISTINCT FROM OLD.details_json
                 OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'reconciliation discrepancy identity is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER reconciliation_discrepancies_identity_immutable BEFORE UPDATE "
            "ON reconciliation_discrepancies FOR EACH ROW "
            "EXECUTE FUNCTION reject_reconciliation_discrepancy_identity_mutation()"
        )
        op.execute(
            "CREATE TRIGGER reconciliation_runs_no_delete BEFORE DELETE ON reconciliation_runs "
            "FOR EACH ROW EXECUTE FUNCTION reject_reconciliation_entry_mutation()"
        )
        op.execute(
            "CREATE TRIGGER reconciliation_discrepancies_no_delete BEFORE DELETE "
            "ON reconciliation_discrepancies FOR EACH ROW "
            "EXECUTE FUNCTION reject_reconciliation_entry_mutation()"
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS reconciliation_entries_no_update")
        op.execute("DROP TRIGGER IF EXISTS reconciliation_entries_no_delete")
        op.execute("DROP TRIGGER IF EXISTS reconciliation_runs_identity_immutable")
        op.execute("DROP TRIGGER IF EXISTS reconciliation_discrepancies_identity_immutable")
        op.execute("DROP TRIGGER IF EXISTS reconciliation_runs_no_delete")
        op.execute("DROP TRIGGER IF EXISTS reconciliation_discrepancies_no_delete")
    elif dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS reconciliation_entries_immutable ON reconciliation_entries"
        )
        op.execute("DROP TRIGGER IF EXISTS reconciliation_runs_no_delete ON reconciliation_runs")
        op.execute(
            "DROP TRIGGER IF EXISTS reconciliation_discrepancies_no_delete "
            "ON reconciliation_discrepancies"
        )
        op.execute("DROP FUNCTION IF EXISTS reject_reconciliation_entry_mutation()")
        op.execute(
            "DROP TRIGGER IF EXISTS reconciliation_runs_identity_immutable ON reconciliation_runs"
        )
        op.execute("DROP FUNCTION IF EXISTS reject_reconciliation_run_identity_mutation()")
        op.execute(
            "DROP TRIGGER IF EXISTS reconciliation_discrepancies_identity_immutable "
            "ON reconciliation_discrepancies"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS reject_reconciliation_discrepancy_identity_mutation()"
        )
    op.drop_index("ix_reconciliation_discrepancies_kind", table_name="reconciliation_discrepancies")
    op.drop_index("ix_reconciliation_discrepancies_run_id", table_name="reconciliation_discrepancies")
    op.drop_table("reconciliation_discrepancies")
    op.drop_index("ix_reconciliation_entries_provider_reference", table_name="reconciliation_entries")
    op.drop_index("ix_reconciliation_entries_provider_operation_id", table_name="reconciliation_entries")
    op.drop_index("ix_reconciliation_entries_run_id", table_name="reconciliation_entries")
    op.drop_table("reconciliation_entries")
    op.drop_index("ix_reconciliation_runs_provider", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
    op.drop_column("bookings", "payout_block_reason")
    op.drop_column("bookings", "payout_blocked")
    op.drop_index("uq_payments_provider_reference", table_name="payments")
    op.drop_column("payments", "provider_merchant")
    op.drop_column("payments", "provider_reference")
