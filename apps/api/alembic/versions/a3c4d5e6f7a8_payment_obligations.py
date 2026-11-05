"""Split booking money into explicit payment obligations.

Revision ID: a3c4d5e6f7a8
Revises: f2b3c4d5e6f7
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "a3c4d5e6f7a8"
down_revision: str | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offer_versions",
        sa.Column("advance_rub", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offer_versions",
        sa.Column("balance_rub", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offer_versions",
        sa.Column("security_deposit_rub", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "payment_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "offer_version_id",
            sa.String(length=36),
            sa.ForeignKey("offer_versions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_plans_offer_version_id", "payment_plans", ["offer_version_id"])
    op.create_table(
        "payment_obligations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("payment_plans.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("recipient", sa.String(length=32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("satisfied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("plan_id", "kind"),
    )
    op.create_index("ix_payment_obligations_plan_id", "payment_obligations", ["plan_id"])
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("obligation_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_payments_obligation_id_payment_obligations",
            "payment_obligations",
            ["obligation_id"],
            ["id"],
        )
        batch_op.create_index("ix_payments_obligation_id", ["obligation_id"])

    bind = op.get_bind()
    created_at = datetime.now(timezone.utc)
    versions = bind.execute(
        sa.text("SELECT id, total_rub, currency FROM offer_versions")
    ).mappings()
    obligation_by_version: dict[str, str] = {}
    for version in versions:
        plan_id = str(uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO payment_plans (id, offer_version_id, currency, created_at) "
                "VALUES (:id, :version_id, :currency, :created_at)"
            ),
            {
                "id": plan_id,
                "version_id": version["id"],
                "currency": version["currency"],
                "created_at": created_at,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE offer_versions SET advance_rub = total_rub, balance_rub = 0, "
                "security_deposit_rub = 0 WHERE id = :version_id"
            ),
            {"version_id": version["id"]},
        )
        for kind, amount in (
            ("advance", version["total_rub"]),
            ("balance", 0),
            ("security_deposit", 0),
        ):
            obligation_id = str(uuid4())
            bind.execute(
                sa.text(
                    "INSERT INTO payment_obligations "
                    "(id, plan_id, kind, amount_rub, recipient, status, created_at) "
                    "VALUES (:id, :plan_id, :kind, :amount, 'supplier', :status, :created_at)"
                ),
                {
                    "id": obligation_id,
                    "plan_id": plan_id,
                    "kind": kind,
                    "amount": amount,
                    "status": "pending" if amount > 0 else "not_applicable",
                    "created_at": created_at,
                },
            )
            if kind == "advance":
                obligation_by_version[version["id"]] = obligation_id

    payments = bind.execute(
        sa.text(
            "SELECT p.id, COALESCE(b.accepted_offer_version_id, o.active_version_id) AS version_id "
            "FROM payments p JOIN bookings b ON b.id = p.booking_id "
            "JOIN offers o ON o.id = b.offer_id"
        )
    ).mappings()
    for payment in payments:
        obligation_id = obligation_by_version.get(payment["version_id"])
        if obligation_id:
            bind.execute(
                sa.text("UPDATE payments SET obligation_id = :oid WHERE id = :payment_id"),
                {"oid": obligation_id, "payment_id": payment["id"]},
            )


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_index("ix_payments_obligation_id")
        batch_op.drop_constraint(
            "fk_payments_obligation_id_payment_obligations",
            type_="foreignkey",
        )
        batch_op.drop_column("obligation_id")
    op.drop_index("ix_payment_obligations_plan_id", table_name="payment_obligations")
    op.drop_table("payment_obligations")
    op.drop_index("ix_payment_plans_offer_version_id", table_name="payment_plans")
    op.drop_table("payment_plans")
    op.drop_column("offer_versions", "security_deposit_rub")
    op.drop_column("offer_versions", "balance_rub")
    op.drop_column("offer_versions", "advance_rub")
