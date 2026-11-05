"""Record external transfer reports separately from provider captures.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_payment_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("payment_id", sa.String(length=36), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("submitted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_external_payment_reports_payment_id", "external_payment_reports", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_external_payment_reports_payment_id", table_name="external_payment_reports")
    op.drop_table("external_payment_reports")
