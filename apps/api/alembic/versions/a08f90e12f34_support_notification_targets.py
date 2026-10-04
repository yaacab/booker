"""Explicit support notification targets, initially without external addresses.

Revision ID: a08f90e12f34
Revises: a07f89e01f23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a08f90e12f34"
down_revision: str | None = "a07f89e01f23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "support_notification_targets" in inspector.get_table_names():
        columns = {row["name"] for row in inspector.get_columns("support_notification_targets")}
        unique_sets = {
            tuple(row.get("column_names") or ())
            for row in inspector.get_unique_constraints("support_notification_targets")
        }
        foreign_keys = inspector.get_foreign_keys("support_notification_targets")
        indexes = {row.get("name") for row in inspector.get_indexes("support_notification_targets")}
        if (
            not {"id", "recipient_user_id", "channel", "escalation_level", "active",
                 "schedule_json", "state_version", "created_at", "updated_at"} <= columns
            or ("recipient_user_id", "channel", "escalation_level") not in unique_sets
            or not any(fk.get("constrained_columns") == ["recipient_user_id"]
                       and fk.get("referred_table") == "users" for fk in foreign_keys)
            or "uq_support_notification_target_active_staff_level" not in indexes
        ):
            raise RuntimeError("Existing support target table requires schema review")
        return
    op.create_table(
        "support_notification_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("escalation_level", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("schedule_json", sa.Text(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("recipient_user_id", "channel", "escalation_level",
                            name="uq_support_notification_target"),
        sa.CheckConstraint("channel IN ('cabinet','email','telegram')",
                           name="ck_support_notification_target_channel"),
        sa.CheckConstraint("escalation_level IN ('primary','backup','administrator')",
                           name="ck_support_notification_target_level"),
    )
    op.create_index(
        "ix_support_notification_targets_recipient_user_id",
        "support_notification_targets", ["recipient_user_id"],
    )
    op.create_index(
        "uq_support_notification_target_active_staff_level",
        "support_notification_targets", ["channel", "escalation_level"], unique=True,
        sqlite_where=sa.text("active = 1 AND escalation_level IN ('primary','backup')"),
        postgresql_where=sa.text("active = true AND escalation_level IN ('primary','backup')"),
    )


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing support target configuration")
