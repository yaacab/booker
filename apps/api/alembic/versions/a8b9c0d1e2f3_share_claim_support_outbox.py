"""shared shortlists, venue claims, support tickets, email outbox

Revision ID: a8b9c0d1e2f3
Revises: f7a3b4c5d6e7
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_shortlists",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shared_shortlists_token", "shared_shortlists", ["token"], unique=True)
    op.create_index("ix_shared_shortlists_owner_user_id", "shared_shortlists", ["owner_user_id"])
    op.create_index("ix_shared_shortlists_organization_id", "shared_shortlists", ["organization_id"])

    op.create_table(
        "shared_shortlist_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "shortlist_id",
            sa.String(length=36),
            sa.ForeignKey("shared_shortlists.id"),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_shared_shortlist_items_shortlist_id", "shared_shortlist_items", ["shortlist_id"])
    op.create_index("ix_shared_shortlist_items_target_id", "shared_shortlist_items", ["target_id"])

    op.create_table(
        "venue_ownership_claims",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("venue_id", sa.String(length=36), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column(
            "claimant_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "claimant_org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("evidence_note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_venue_ownership_claims_venue_id", "venue_ownership_claims", ["venue_id"])
    op.create_index("ix_venue_ownership_claims_status", "venue_ownership_claims", ["status"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("author_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("related_type", sa.String(length=32), nullable=True),
        sa.Column("related_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_support_tickets_author_user_id", "support_tickets", ["author_user_id"])
    op.create_index("ix_support_tickets_category", "support_tickets", ["category"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_outbox_idempotency_key", "email_outbox", ["idempotency_key"], unique=True)
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"])


def downgrade() -> None:
    op.drop_table("email_outbox")
    op.drop_table("support_tickets")
    op.drop_table("venue_ownership_claims")
    op.drop_table("shared_shortlist_items")
    op.drop_table("shared_shortlists")
