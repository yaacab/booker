"""venue catalog lifecycle, provenance and moderation

Revision ID: c8d9e0f1a2b3
Revises: b1c2d3e4f5a7
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b1c2d3e4f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = (
        sa.Column("venue_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("administrative_district", sa.String(32), nullable=False, server_default=""),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("official_website", sa.String(512), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="owner_submission"),
        sa.Column("partnership_status", sa.String(32), nullable=False, server_default="claimed"),
        sa.Column("is_partner", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_claimed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("moderation_status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("completeness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(36), nullable=True),
        sa.Column("partnership_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "data_freshness_status",
            sa.String(32),
            nullable=False,
            server_default="needs_review",
        ),
    )
    for column in columns:
        op.add_column("venues", column)

    op.execute(
        """UPDATE venues SET
        source_type = CASE WHEN listing_origin = 'open_data' THEN 'automated_import'
                           WHEN listing_origin = 'owner' THEN 'owner_submission' ELSE 'manual' END,
        partnership_status = CASE WHEN verified = true THEN 'verified'
                                  WHEN listing_origin = 'owner' THEN 'claimed' ELSE 'unverified_listing' END,
        is_claimed = CASE WHEN listing_origin = 'owner' OR verified = true THEN true ELSE false END,
        moderation_status = CASE WHEN listing_origin = 'open_data' THEN 'needs_review' ELSE 'published' END,
        completeness_score = CASE WHEN listing_origin = 'open_data' THEN 0 ELSE 100 END
        """
    )

    op.create_table(
        "venue_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("venue_id", sa.String(36), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("venue_id", "field_name", "source_url"),
    )
    op.create_index("ix_venue_sources_venue_id", "venue_sources", ["venue_id"])
    op.create_table(
        "venue_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("venue_id", sa.String(36), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("photo_url", sa.String(1024), nullable=False),
        sa.Column("photo_source_url", sa.String(1024), nullable=False),
        sa.Column("photo_rights_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("venue_id", "photo_url"),
    )
    op.create_index("ix_venue_photos_venue_id", "venue_photos", ["venue_id"])
    op.create_table(
        "venue_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("venue_id", sa.String(36), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("old_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("changed_by", sa.String(36), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_venue_status_history_venue_id", "venue_status_history", ["venue_id"])
    op.create_table(
        "venue_import_batches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(128), nullable=False, server_default="Москва"),
        sa.Column("category", sa.String(64), nullable=False, server_default="mixed"),
        sa.Column(
            "administrative_district",
            sa.String(32),
            nullable=False,
            server_default="all",
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("with_contacts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("with_prices_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("with_photos_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "with_official_website_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "venue_duplicate_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(64),
            sa.ForeignKey("venue_import_batches.id"),
            nullable=False,
        ),
        sa.Column(
            "incoming_key",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "existing_venue_id",
            sa.String(36),
            sa.ForeignKey("venues.id"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("resolution", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_venue_duplicate_candidates_batch_id",
        "venue_duplicate_candidates",
        ["batch_id"],
    )
    op.create_index(
        "ix_venue_duplicate_candidates_existing_venue_id",
        "venue_duplicate_candidates",
        ["existing_venue_id"],
    )


def downgrade() -> None:
    op.drop_table("venue_duplicate_candidates")
    op.drop_table("venue_import_batches")
    op.drop_table("venue_status_history")
    op.drop_table("venue_photos")
    op.drop_table("venue_sources")
    for column in (
        "data_freshness_status",
        "last_crawled_at",
        "last_verified_at",
        "status_changed_at",
        "partnership_started_at",
        "verified_by",
        "verified_at",
        "details_json",
        "completeness_score",
        "moderation_status",
        "is_claimed",
        "is_partner",
        "partnership_status",
        "source_type",
        "official_website",
        "email",
        "phone",
        "longitude",
        "latitude",
        "administrative_district",
        "venue_type",
    ):
        op.drop_column("venues", column)
