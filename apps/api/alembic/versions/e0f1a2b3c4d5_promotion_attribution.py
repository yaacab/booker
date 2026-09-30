"""Promotion monthly credits and scoped conversion attribution."""

from alembic import op
import sqlalchemy as sa

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promotion_credit_uses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["promotion_campaigns.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_promo_credit_key"),
    )
    op.create_index(
        op.f("ix_promotion_credit_uses_organization_id"),
        "promotion_credit_uses",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_promotion_credit_uses_period_key"),
        "promotion_credit_uses",
        ["period_key"],
        unique=False,
    )
    op.create_table(
        "promotion_touches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impressed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_org_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("booking_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["promotion_campaigns.id"],
        ),
        sa.ForeignKeyConstraint(
            ["customer_org_id"],
            ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        op.f("ix_promotion_touches_campaign_id"), "promotion_touches", ["campaign_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_promotion_touches_campaign_id"), table_name="promotion_touches")
    op.drop_table("promotion_touches")
    op.drop_index(op.f("ix_promotion_credit_uses_period_key"), table_name="promotion_credit_uses")
    op.drop_index(
        op.f("ix_promotion_credit_uses_organization_id"), table_name="promotion_credit_uses"
    )
    op.drop_table("promotion_credit_uses")
