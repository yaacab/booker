"""Add hashed one-time staff recovery codes.

Revision ID: a03f45a67b89
Revises: a02e34f56a78
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a03f45a67b89"
down_revision: str | None = "a02e34f56a78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("staff_recovery_codes"):
        op.create_table(
            "staff_recovery_codes",
            sa.Column("code_hash", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("staff_recovery_codes")}
    primary_key = inspector.get_pk_constraint("staff_recovery_codes").get("constrained_columns")
    foreign_keys = inspector.get_foreign_keys("staff_recovery_codes")
    if (
        not {"code_hash", "user_id", "issued_at", "used_at"} <= columns
        or primary_key != ["code_hash"]
        or not any(
            fk.get("constrained_columns") == ["user_id"]
            and fk.get("referred_table") == "users"
            and fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
    ):
        raise RuntimeError("staff recovery table requires schema review")
    indexes = {index["name"] for index in inspector.get_indexes("staff_recovery_codes")}
    if "ix_staff_recovery_codes_user_id" not in indexes:
        op.create_index("ix_staff_recovery_codes_user_id", "staff_recovery_codes", ["user_id"])


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing staff recovery evidence")
