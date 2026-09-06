"""venue open data fields

Revision ID: b3f8a1c2d4e5
Revises: ad7ec0cd0ee2
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3f8a1c2d4e5"
down_revision: Union[str, None] = "ad7ec0cd0ee2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("venues", sa.Column("address", sa.String(length=512), nullable=False, server_default=""))
    op.add_column("venues", sa.Column("district", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("venues", sa.Column("metro", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("venues", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("venues", sa.Column("source_url", sa.String(length=512), nullable=False, server_default=""))
    op.add_column(
        "venues", sa.Column("source_attribution", sa.String(length=128), nullable=False, server_default="")
    )
    op.add_column(
        "venues", sa.Column("listing_origin", sa.String(length=32), nullable=False, server_default="owner")
    )
    op.add_column(
        "venues", sa.Column("availability_mode", sa.String(length=32), nullable=False, server_default="owner")
    )


def downgrade() -> None:
    op.drop_column("venues", "availability_mode")
    op.drop_column("venues", "listing_origin")
    op.drop_column("venues", "source_attribution")
    op.drop_column("venues", "source_url")
    op.drop_column("venues", "description")
    op.drop_column("venues", "metro")
    op.drop_column("venues", "district")
    op.drop_column("venues", "address")
