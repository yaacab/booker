"""Add expiring organization invitations.

Revision ID: d6f7a8b9c0d1
Revises: c5e6f7a8b9c0
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6f7a8b9c0d1"
down_revision: str | None = "c5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("invited_user_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("can_confirm_offer", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.UniqueConstraint(
            "organization_id",
            "invited_by_user_id",
            "idempotency_key",
            name="uq_organization_invitation_actor_idempotency",
        ),
    )
    op.create_index(
        "ix_organization_invitations_organization_id",
        "organization_invitations",
        ["organization_id"],
    )
    op.create_index("ix_organization_invitations_email", "organization_invitations", ["email"])
    op.create_index("ix_organization_invitations_status", "organization_invitations", ["status"])
    pending = sa.text("status = 'pending'")
    op.create_index(
        "uq_organization_invitation_pending_email",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        sqlite_where=pending,
        postgresql_where=pending,
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM organization_invitations")).scalar_one():
        raise RuntimeError("Refusing to drop non-empty organization invitation history")
    op.drop_index(
        "uq_organization_invitation_pending_email", table_name="organization_invitations"
    )
    op.drop_index("ix_organization_invitations_status", table_name="organization_invitations")
    op.drop_index("ix_organization_invitations_email", table_name="organization_invitations")
    op.drop_index(
        "ix_organization_invitations_organization_id", table_name="organization_invitations"
    )
    op.drop_table("organization_invitations")
