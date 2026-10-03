"""Add support urgency and response targets.

Revision ID: ea1d2e3f4a5b
Revises: e9c0d1e2f3a4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ea1d2e3f4a5b"
down_revision: str | None = "e9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("support_tickets")}
    if "priority" not in columns:
        op.add_column(
            "support_tickets",
            sa.Column("priority", sa.String(length=16), server_default="normal", nullable=False),
        )
    if "urgency_code" not in columns:
        op.add_column(
            "support_tickets",
            sa.Column("urgency_code", sa.String(length=32), nullable=True),
        )
    if "response_due_at" not in columns:
        op.add_column(
            "support_tickets",
            sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
        )

    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("support_tickets")}
    if "ix_support_tickets_priority" not in indexes:
        op.create_index("ix_support_tickets_priority", "support_tickets", ["priority"])
    if "ix_support_tickets_urgency_code" not in indexes:
        op.create_index("ix_support_tickets_urgency_code", "support_tickets", ["urgency_code"])
    if "ix_support_tickets_response_due_at" not in indexes:
        op.create_index(
            "ix_support_tickets_response_due_at", "support_tickets", ["response_due_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    urgent_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM support_tickets WHERE priority <> 'normal' "
            "OR urgency_code IS NOT NULL OR response_due_at IS NOT NULL"
        )
    ).scalar_one()
    if urgent_count:
        raise RuntimeError("Refusing to drop populated support SLA metadata")
    op.drop_index("ix_support_tickets_response_due_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_urgency_code", table_name="support_tickets")
    op.drop_index("ix_support_tickets_priority", table_name="support_tickets")
    op.drop_column("support_tickets", "response_due_at")
    op.drop_column("support_tickets", "urgency_code")
    op.drop_column("support_tickets", "priority")
