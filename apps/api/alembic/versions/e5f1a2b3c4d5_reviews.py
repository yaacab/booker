"""reviews table for Completed bookings

Revision ID: e5f1a2b3c4d5
Revises: d4e8b2a9c1f0
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f1a2b3c4d5"
down_revision: Union[str, None] = "d4e8b2a9c1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("booking_id", "author_user_id"),
    )
    op.create_index("ix_reviews_booking_id", "reviews", ["booking_id"])
    op.create_index("ix_reviews_author_user_id", "reviews", ["author_user_id"])
    op.create_index("ix_reviews_org_id", "reviews", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_org_id", table_name="reviews")
    op.drop_index("ix_reviews_author_user_id", table_name="reviews")
    op.drop_index("ix_reviews_booking_id", table_name="reviews")
    op.drop_table("reviews")
