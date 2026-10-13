"""Bind bookings to the accepted offer version.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from booker_api.offer_version_binding import backfill_accepted_offer_versions

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings", sa.Column("accepted_offer_version_id", sa.String(length=36), nullable=True)
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_bookings_accepted_offer_version_id_offer_versions",
            "bookings",
            "offer_versions",
            ["accepted_offer_version_id"],
            ["id"],
        )
    backfill_accepted_offer_versions(op.get_bind())


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_bookings_accepted_offer_version_id_offer_versions", "bookings", type_="foreignkey"
        )
    op.drop_column("bookings", "accepted_offer_version_id")
