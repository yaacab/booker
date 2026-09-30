"""Deduplicated supply discovery observations."""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("visitor_key", sa.String(64), nullable=False),
        sa.Column("day_key", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "target_type", "target_id", "kind", "visitor_key", "day_key", name="uq_discovery_daily"
        ),
        sa.CheckConstraint(
            "kind IN ('impression', 'profile_view', 'favorite')", name="ck_discovery_kind"
        ),
    )
    for col in ("organization_id", "target_id", "created_at"):
        op.create_index(f"ix_discovery_signals_{col}", "discovery_signals", [col])


def downgrade():
    op.drop_table("discovery_signals")
