"""Stable server receipt time for inbox activity ordering.

Revision ID: f8b4c5d6e7f8
Revises: f5b0c1d2e3f4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8b4c5d6e7f8"
down_revision: str | None = "f5b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("messages")}
    if "received_at" not in columns:
        op.add_column(
            "messages",
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        )
    # Legacy chronology cannot be reconstructed when created_at was wrong. In
    # particular, a future-dated legacy row must not outrank new activity.
    op.execute(
        "UPDATE messages SET received_at = CASE "
        "WHEN created_at > CURRENT_TIMESTAMP THEN CURRENT_TIMESTAMP "
        "ELSE created_at END WHERE received_at IS NULL"
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM messages LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated message receipt times")
    op.drop_column("messages", "received_at")
