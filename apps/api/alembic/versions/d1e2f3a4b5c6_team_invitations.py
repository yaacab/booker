"""Scoped expiring invitations to organization teams."""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("team_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("can_confirm_offer", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("accepted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_team_invitations_organization_id", "team_invitations", ["organization_id"])


def downgrade():
    op.drop_table("team_invitations")
