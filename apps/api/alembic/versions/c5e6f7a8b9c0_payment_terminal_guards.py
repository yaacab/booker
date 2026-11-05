"""Prevent concurrent duplicate payment, capture, and refund operations.

Revision ID: c5e6f7a8b9c0
Revises: b4d5e6f7a8b9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5e6f7a8b9c0"
down_revision: str | None = "b4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    active_payment = sa.text(
        "obligation_id IS NOT NULL AND status IN ('pending', 'succeeded', 'external_recorded')"
    )
    op.create_index(
        "uq_payments_active_obligation",
        "payments",
        ["obligation_id"],
        unique=True,
        sqlite_where=active_payment,
        postgresql_where=active_payment,
    )
    capture = sa.text("kind = 'capture'")
    op.create_index(
        "uq_money_movement_capture_payment",
        "money_movements",
        ["payment_id"],
        unique=True,
        sqlite_where=capture,
        postgresql_where=capture,
    )
    pending_refund = sa.text("status = 'pending'")
    op.create_index(
        "uq_refund_request_pending_payment",
        "refund_requests",
        ["payment_id"],
        unique=True,
        sqlite_where=pending_refund,
        postgresql_where=pending_refund,
    )


def downgrade() -> None:
    op.drop_index("uq_refund_request_pending_payment", table_name="refund_requests")
    op.drop_index("uq_money_movement_capture_payment", table_name="money_movements")
    op.drop_index("uq_payments_active_obligation", table_name="payments")
