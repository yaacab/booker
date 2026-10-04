"""Add an append-only ledger for captured and refunded provider funds.

Revision ID: b4d5e6f7a8b9
Revises: a3c4d5e6f7a8
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "b4d5e6f7a8b9"
down_revision: str | None = "a3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _install_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER money_movements_no_update BEFORE UPDATE ON money_movements "
            "BEGIN SELECT RAISE(ABORT, 'money_movements is append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER money_movements_no_delete BEFORE DELETE ON money_movements "
            "BEGIN SELECT RAISE(ABORT, 'money_movements is append-only'); END"
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION reject_money_movement_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'money_movements is append-only'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            "CREATE TRIGGER money_movements_no_update BEFORE UPDATE ON money_movements "
            "FOR EACH ROW EXECUTE FUNCTION reject_money_movement_mutation()"
        )
        op.execute(
            "CREATE TRIGGER money_movements_no_delete BEFORE DELETE ON money_movements "
            "FOR EACH ROW EXECUTE FUNCTION reject_money_movement_mutation()"
        )


def upgrade() -> None:
    op.create_table(
        "money_movements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("payment_id", sa.String(length=36), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column(
            "obligation_id",
            sa.String(length=36),
            sa.ForeignKey("payment_obligations.id"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_rub > 0", name="ck_money_movement_positive_amount"),
        sa.CheckConstraint(
            "direction IN ('credit', 'debit')", name="ck_money_movement_direction"
        ),
        sa.UniqueConstraint("source_type", "source_id", "kind", name="uq_money_movement_source"),
    )
    op.create_index("ix_money_movements_booking_id", "money_movements", ["booking_id"])
    op.create_index("ix_money_movements_payment_id", "money_movements", ["payment_id"])
    op.create_index("ix_money_movements_obligation_id", "money_movements", ["obligation_id"])

    bind = op.get_bind()
    created_at = datetime.now(timezone.utc)
    bind.execute(
        sa.text(
            "UPDATE payments SET status = 'external_recorded' "
            "WHERE provider = 'external' AND status = 'succeeded'"
        )
    )
    rows = bind.execute(
        sa.text(
            "SELECT id, booking_id, obligation_id, amount_rub, provider, status "
            "FROM payments WHERE provider <> 'external' "
            "AND status IN ('succeeded', 'refunded', 'partially_refunded')"
        )
    ).mappings()
    for row in rows:
        capture_id = str(uuid4())
        metadata = '{"backfill":true}'
        bind.execute(
            sa.text(
                "INSERT INTO money_movements "
                "(id, booking_id, payment_id, obligation_id, kind, direction, amount_rub, "
                "currency, provider, source_type, source_id, metadata_json, created_at) "
                "VALUES (:id, :booking_id, :payment_id, :obligation_id, 'capture', 'credit', "
                ":amount, 'RUB', :provider, 'migration', :source_id, :metadata, :created_at)"
            ),
            {
                "id": capture_id,
                "booking_id": row["booking_id"],
                "payment_id": row["id"],
                "obligation_id": row["obligation_id"],
                "amount": row["amount_rub"],
                "provider": row["provider"],
                "source_id": row["id"],
                "metadata": metadata,
                "created_at": created_at,
            },
        )
        refund_amount = 0
        if row["status"] == "refunded":
            refund_amount = row["amount_rub"]
        elif row["status"] == "partially_refunded":
            refund_amount = (
                bind.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(amount_rub), 0) FROM refund_requests "
                        "WHERE payment_id = :payment_id AND status = 'refunded'"
                    ),
                    {"payment_id": row["id"]},
                ).scalar_one()
            )
            if refund_amount <= 0 or refund_amount >= row["amount_rub"]:
                raise RuntimeError(
                    "Cannot backfill partially_refunded payment without a verified partial amount: "
                    f"{row['id']}"
                )
        if refund_amount:
            bind.execute(
                sa.text(
                    "INSERT INTO money_movements "
                    "(id, booking_id, payment_id, obligation_id, kind, direction, amount_rub, "
                    "currency, provider, source_type, source_id, metadata_json, created_at) "
                    "VALUES (:id, :booking_id, :payment_id, :obligation_id, 'refund', 'debit', "
                    ":amount, 'RUB', :provider, 'migration-refund', :source_id, :metadata, :created_at)"
                ),
                {
                    "id": str(uuid4()),
                    "booking_id": row["booking_id"],
                    "payment_id": row["id"],
                    "obligation_id": row["obligation_id"],
                    "amount": refund_amount,
                    "provider": row["provider"],
                    "source_id": row["id"],
                    "metadata": metadata,
                    "created_at": created_at,
                },
            )
    _install_append_only_guards()


def downgrade() -> None:
    bind = op.get_bind()
    movement_count = bind.execute(sa.text("SELECT COUNT(*) FROM money_movements")).scalar_one()
    if movement_count:
        raise RuntimeError(
            "Refusing to drop non-empty money_movements; export and reconcile the ledger first"
        )
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS money_movements_no_update")
        op.execute("DROP TRIGGER IF EXISTS money_movements_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS money_movements_no_update ON money_movements")
        op.execute("DROP TRIGGER IF EXISTS money_movements_no_delete ON money_movements")
        op.execute("DROP FUNCTION IF EXISTS reject_money_movement_mutation()")
    op.drop_index("ix_money_movements_obligation_id", table_name="money_movements")
    op.drop_index("ix_money_movements_payment_id", table_name="money_movements")
    op.drop_index("ix_money_movements_booking_id", table_name="money_movements")
    op.drop_table("money_movements")
