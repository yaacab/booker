"""public briefs and brief responses

Revision ID: f7a3b4c5d6e7
Revises: e5f1a2b3c4d5
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a3b4c5d6e7"
# Favorites (f6a2b3c4d5e6) may land first; coordinator rewires chain on integrate.
down_revision: Union[str, None] = "e5f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "public_briefs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=36),
            sa.ForeignKey("events.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role_needed", sa.String(length=64), nullable=False),
        sa.Column("guest_count_band", sa.String(length=32), nullable=False),
        sa.Column("public_notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_public_briefs_organization_id", "public_briefs", ["organization_id"])
    op.create_index("ix_public_briefs_created_by_user_id", "public_briefs", ["created_by_user_id"])
    op.create_index("ix_public_briefs_event_id", "public_briefs", ["event_id"])
    op.create_index("ix_public_briefs_role_needed", "public_briefs", ["role_needed"])
    op.create_index("ix_public_briefs_status", "public_briefs", ["status"])

    op.create_table(
        "brief_responses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "brief_id",
            sa.String(length=36),
            sa.ForeignKey("public_briefs.id"),
            nullable=False,
        ),
        sa.Column(
            "supplier_org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("brief_id", "supplier_org_id"),
    )
    op.create_index("ix_brief_responses_brief_id", "brief_responses", ["brief_id"])
    op.create_index("ix_brief_responses_supplier_org_id", "brief_responses", ["supplier_org_id"])
    op.create_index("ix_brief_responses_author_user_id", "brief_responses", ["author_user_id"])


def downgrade() -> None:
    op.drop_index("ix_brief_responses_author_user_id", table_name="brief_responses")
    op.drop_index("ix_brief_responses_supplier_org_id", table_name="brief_responses")
    op.drop_index("ix_brief_responses_brief_id", table_name="brief_responses")
    op.drop_table("brief_responses")
    op.drop_index("ix_public_briefs_status", table_name="public_briefs")
    op.drop_index("ix_public_briefs_role_needed", table_name="public_briefs")
    op.drop_index("ix_public_briefs_event_id", table_name="public_briefs")
    op.drop_index("ix_public_briefs_created_by_user_id", table_name="public_briefs")
    op.drop_index("ix_public_briefs_organization_id", table_name="public_briefs")
    op.drop_table("public_briefs")
