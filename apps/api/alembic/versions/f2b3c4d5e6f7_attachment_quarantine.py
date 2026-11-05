"""Quarantine deal attachments until scan review.

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deal_attachments",
        sa.Column("scan_status", sa.String(length=32), nullable=False, server_default="quarantined"),
    )
    op.add_column("deal_attachments", sa.Column("scan_note", sa.Text(), nullable=False, server_default=""))
    op.add_column("deal_attachments", sa.Column("scanned_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("deal_attachments", sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("deal_attachments", "scanned_at")
    op.drop_column("deal_attachments", "scanned_by_user_id")
    op.drop_column("deal_attachments", "scan_note")
    op.drop_column("deal_attachments", "scan_status")
