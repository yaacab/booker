"""Record scanner provenance for attachment access.

Revision ID: f9c5d6e7f8a9
Revises: f8b4c5d6e7f8
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f9c5d6e7f8a9"
down_revision: str | None = "f8b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("deal_attachments")}
    if "av_verdict_provider" not in columns:
        op.add_column("deal_attachments", sa.Column("av_verdict_provider", sa.String(32)))
    if "av_verdict_sha256" not in columns:
        op.add_column("deal_attachments", sa.Column("av_verdict_sha256", sa.String(64)))
    if "av_scan_token" not in columns:
        op.add_column("deal_attachments", sa.Column("av_scan_token", sa.String(36)))
    if "av_scan_started_at" not in columns:
        op.add_column("deal_attachments", sa.Column("av_scan_started_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("deal_attachments", "av_scan_started_at")
    op.drop_column("deal_attachments", "av_scan_token")
    op.drop_column("deal_attachments", "av_verdict_sha256")
    op.drop_column("deal_attachments", "av_verdict_provider")
