"""Recipient-indexed safe notification inbox.

Revision ID: a05f67c89d01
Revises: a04f56b78c90
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a05f67c89d01"
down_revision: str | None = "a04f56b78c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("user_notifications"):
        op.create_table(
            "user_notifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("recipient_user_id", sa.String(36),
                      sa.ForeignKey("users.id"), nullable=False),
            sa.Column("template", sa.String(64), nullable=False),
            sa.Column("entity_type", sa.String(32), nullable=False),
            sa.Column("entity_id", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("recipient_user_id", "template", "entity_type", "entity_id",
                                name="uq_user_notification_event"),
        )
        inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns("user_notifications")}
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("user_notifications")
    }
    foreign_keys = inspector.get_foreign_keys("user_notifications")
    if (
        set(columns) != {"id", "recipient_user_id", "template", "entity_type",
                         "entity_id", "created_at"}
        or any(columns[name]["nullable"] for name in columns)
        or inspector.get_pk_constraint("user_notifications").get("constrained_columns") != ["id"]
        or ("recipient_user_id", "template", "entity_type", "entity_id") not in unique_sets
        or not any(
            fk.get("constrained_columns") == ["recipient_user_id"]
            and fk.get("referred_table") == "users"
            and fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
    ):
        raise RuntimeError("user notifications table requires schema review")
    indexes = {index["name"] for index in inspector.get_indexes("user_notifications")}
    if "ix_user_notifications_recipient_created" not in indexes:
        op.create_index(
            "ix_user_notifications_recipient_created", "user_notifications",
            ["recipient_user_id", "created_at"],
        )


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing user notification evidence")
