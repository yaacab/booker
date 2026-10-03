"""Persist shared, expiring rate-limit counters.

Revision ID: fa6d7e8f901b
Revises: f9c5d6e7f8a9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fa6d7e8f901b"
down_revision: str | None = "f9c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "rate_limit_counters" not in inspector.get_table_names():
        op.create_table(
            "rate_limit_counters",
            sa.Column("bucket_key", sa.String(64), primary_key=True),
            sa.Column("expires_at", sa.BigInteger(), nullable=False),
            sa.Column("hits", sa.Integer(), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("rate_limit_counters")}
    if "ix_rate_limit_counters_expires_at" not in indexes:
        op.create_index(
            "ix_rate_limit_counters_expires_at",
            "rate_limit_counters",
            ["expires_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_expires_at", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
