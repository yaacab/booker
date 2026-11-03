"""Optional client metadata on session_tokens for profile session list."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c13a45b67c89"
down_revision = "b12f34e56a78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {row["name"] for row in sa.inspect(bind).get_columns("session_tokens")}
    if "user_agent" not in columns:
        op.add_column("session_tokens", sa.Column("user_agent", sa.String(length=512), nullable=True))
    if "client_ip" not in columns:
        op.add_column("session_tokens", sa.Column("client_ip", sa.String(length=64), nullable=True))
    if "last_seen_at" not in columns:
        op.add_column(
            "session_tokens",
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    raise RuntimeError("manual migration required before dropping session client metadata")
