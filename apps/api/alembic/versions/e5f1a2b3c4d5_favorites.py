"""favorites table

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
        "favorites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            "target_type",
            "target_id",
            name="uq_favorites_user_org_target",
        ),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_organization_id", "favorites", ["organization_id"])
    op.create_index("ix_favorites_target_id", "favorites", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_target_id", table_name="favorites")
    op.drop_index("ix_favorites_organization_id", table_name="favorites")
    op.drop_index("ix_favorites_user_id", table_name="favorites")
    op.drop_table("favorites")
