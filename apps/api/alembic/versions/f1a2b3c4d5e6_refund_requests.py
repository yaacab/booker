"""Require independent approval for refunds.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refund_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("payment_id", sa.String(length=36), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("refund_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refund_requests_payment_id", "refund_requests", ["payment_id"])
    op.create_index("ix_refund_requests_requested_by_user_id", "refund_requests", ["requested_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_refund_requests_requested_by_user_id", table_name="refund_requests")
    op.drop_index("ix_refund_requests_payment_id", table_name="refund_requests")
    op.drop_table("refund_requests")
