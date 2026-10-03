"""Assign support tickets to operators for the bounded admin queue.

Revision ID: fc8f901ab2c3
Revises: fb7e8f901ab2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fc8f901ab2c3"
down_revision: str | None = "fb7e8f901ab2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("support_tickets")}
    if "assigned_to_user_id" not in columns:
        op.add_column("support_tickets", sa.Column("assigned_to_user_id", sa.String(36), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        fks = sa.inspect(op.get_bind()).get_foreign_keys("support_tickets")
        if not any(fk["constrained_columns"] == ["assigned_to_user_id"] for fk in fks):
            op.create_foreign_key("fk_support_tickets_assignee", "support_tickets", "users",
                                  ["assigned_to_user_id"], ["id"])
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("support_tickets")}
    if "ix_support_tickets_assigned_to_user_id" not in indexes:
        op.create_index("ix_support_tickets_assigned_to_user_id", "support_tickets",
                        ["assigned_to_user_id"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_assigned_to_user_id", table_name="support_tickets")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_support_tickets_assignee", "support_tickets", type_="foreignkey")
    op.drop_column("support_tickets", "assigned_to_user_id")
