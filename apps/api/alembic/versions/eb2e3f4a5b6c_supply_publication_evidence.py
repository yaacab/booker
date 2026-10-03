"""Add explicit supply publication evidence.

Revision ID: eb2e3f4a5b6c
Revises: ea1d2e3f4a5b
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "eb2e3f4a5b6c"
down_revision: str | None = "ea1d2e3f4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_user_fk_column(table: str, column: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(36) REFERENCES users(id)"
            )
        )
        return
    op.add_column(
        table,
        sa.Column(column, sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
    )


def upgrade() -> None:
    artist_columns = _columns("artists")
    venue_columns = _columns("venues")
    photo_columns = _columns("venue_photos")
    if "media_source_url" not in artist_columns:
        op.add_column("artists", sa.Column("media_source_url", sa.String(length=512), nullable=True))
    if "media_rights_status" not in _columns("artists"):
        op.add_column(
            "artists",
            sa.Column(
                "media_rights_status",
                sa.String(length=32),
                server_default="unknown",
                nullable=False,
            ),
        )
    if "media_rights_attested_at" not in artist_columns:
        op.add_column(
            "artists", sa.Column("media_rights_attested_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "media_rights_attested_by_user_id" not in artist_columns:
        _add_user_fk_column("artists", "media_rights_attested_by_user_id")
    if "calendar_confirmed_through" not in _columns("artists"):
        op.add_column(
            "artists",
            sa.Column("calendar_confirmed_through", sa.DateTime(timezone=True), nullable=True),
        )
    if "calendar_confirmed_at" not in artist_columns:
        op.add_column(
            "artists", sa.Column("calendar_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "calendar_confirmed_by_user_id" not in artist_columns:
        _add_user_fk_column("artists", "calendar_confirmed_by_user_id")
    if "publication_enabled" not in artist_columns:
        op.add_column(
            "artists",
            sa.Column("publication_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        )
    if "publication_state_version" not in artist_columns:
        op.add_column(
            "artists",
            sa.Column("publication_state_version", sa.Integer(), server_default="0", nullable=False),
        )
    if "calendar_confirmed_through" not in _columns("venues"):
        op.add_column(
            "venues",
            sa.Column("calendar_confirmed_through", sa.DateTime(timezone=True), nullable=True),
        )
    if "calendar_confirmed_at" not in venue_columns:
        op.add_column(
            "venues", sa.Column("calendar_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "calendar_confirmed_by_user_id" not in venue_columns:
        _add_user_fk_column("venues", "calendar_confirmed_by_user_id")
    if "publication_enabled" not in venue_columns:
        op.add_column(
            "venues",
            sa.Column("publication_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        )
    if "publication_state_version" not in venue_columns:
        op.add_column(
            "venues",
            sa.Column("publication_state_version", sa.Integer(), server_default="0", nullable=False),
        )
    if "rights_attested_at" not in photo_columns:
        op.add_column(
            "venue_photos", sa.Column("rights_attested_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "rights_attested_by_user_id" not in photo_columns:
        _add_user_fk_column("venue_photos", "rights_attested_by_user_id")
    if "ix_artists_calendar_confirmed_through" not in _indexes("artists"):
        op.create_index(
            "ix_artists_calendar_confirmed_through",
            "artists",
            ["calendar_confirmed_through"],
        )
    if "ix_venues_calendar_confirmed_through" not in _indexes("venues"):
        op.create_index(
            "ix_venues_calendar_confirmed_through",
            "venues",
            ["calendar_confirmed_through"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    artist_evidence = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM artists WHERE media_rights_status <> 'unknown' "
            "OR media_source_url IS NOT NULL OR media_rights_attested_at IS NOT NULL "
            "OR media_rights_attested_by_user_id IS NOT NULL "
            "OR calendar_confirmed_through IS NOT NULL OR calendar_confirmed_at IS NOT NULL "
            "OR calendar_confirmed_by_user_id IS NOT NULL OR publication_enabled = 1 "
            "OR publication_state_version <> 0"
        )
    ).scalar_one()
    venue_evidence = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM venues WHERE calendar_confirmed_through IS NOT NULL "
            "OR calendar_confirmed_at IS NOT NULL OR calendar_confirmed_by_user_id IS NOT NULL "
            "OR publication_enabled = 1 OR publication_state_version <> 0"
        )
    ).scalar_one()
    photo_evidence = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM venue_photos WHERE rights_attested_at IS NOT NULL "
            "OR rights_attested_by_user_id IS NOT NULL"
        )
    ).scalar_one()
    if artist_evidence or venue_evidence or photo_evidence:
        raise RuntimeError("Refusing to drop populated supply publication evidence")
    op.drop_index("ix_venues_calendar_confirmed_through", table_name="venues")
    op.drop_index("ix_artists_calendar_confirmed_through", table_name="artists")
    op.drop_column("venue_photos", "rights_attested_by_user_id")
    op.drop_column("venue_photos", "rights_attested_at")
    op.drop_column("venues", "publication_state_version")
    op.drop_column("venues", "publication_enabled")
    op.drop_column("venues", "calendar_confirmed_by_user_id")
    op.drop_column("venues", "calendar_confirmed_at")
    op.drop_column("venues", "calendar_confirmed_through")
    op.drop_column("artists", "publication_state_version")
    op.drop_column("artists", "publication_enabled")
    op.drop_column("artists", "calendar_confirmed_by_user_id")
    op.drop_column("artists", "calendar_confirmed_at")
    op.drop_column("artists", "calendar_confirmed_through")
    op.drop_column("artists", "media_rights_attested_by_user_id")
    op.drop_column("artists", "media_rights_attested_at")
    op.drop_column("artists", "media_rights_status")
    op.drop_column("artists", "media_source_url")
