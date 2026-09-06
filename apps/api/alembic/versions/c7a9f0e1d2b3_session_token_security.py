"""session token 2fa + expiry columns

Revision ID: c7a9f0e1d2b3
Revises: b3f8a1c2d4e5
Create Date: 2026-09-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7a9f0e1d2b3"
down_revision: Union[str, None] = "b3f8a1c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_tokens",
        sa.Column("admin_2fa_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_tokens", "expires_at")
    op.drop_column("session_tokens", "admin_2fa_verified_at")
