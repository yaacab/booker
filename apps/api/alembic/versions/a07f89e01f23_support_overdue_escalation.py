"""Record durable first-response escalation of support tickets.

Revision ID: a07f89e01f23
Revises: a06f78d90e12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a07f89e01f23"
down_revision: str | None = "a06f78d90e12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("support_tickets")}
    if "overdue_escalated_at" not in columns:
        op.add_column(
            "support_tickets",
            sa.Column("overdue_escalated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing support escalation evidence")
