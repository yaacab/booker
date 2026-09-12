"""Explicit public brief metadata, saved opportunity filters and delivery deduplication."""

from alembic import op
import sqlalchemy as sa

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("brief_responses", sa.Column("target_type", sa.String(16), nullable=True))
    op.add_column("brief_responses", sa.Column("target_id", sa.String(36), nullable=True))
    op.add_column(
        "public_briefs", sa.Column("event_type", sa.String(64), nullable=False, server_default="")
    )
    op.add_column(
        "public_briefs",
        sa.Column("share_budget", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("public_briefs", sa.Column("budget_min_rub", sa.Integer(), nullable=True))
    op.add_column("public_briefs", sa.Column("budget_max_rub", sa.Integer(), nullable=True))
    op.add_column(
        "public_briefs",
        sa.Column("public_requirements_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "opportunity_filters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("query_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("instant_alerts", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_opportunity_filter_key"),
    )
    op.create_index(
        "ix_opportunity_filters_organization_id", "opportunity_filters", ["organization_id"]
    )
    op.create_index("ix_opportunity_filters_user_id", "opportunity_filters", ["user_id"])
    op.create_table(
        "opportunity_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brief_id", sa.String(36), sa.ForeignKey("public_briefs.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "filter_id", sa.String(36), sa.ForeignKey("opportunity_filters.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("brief_id", "user_id", name="uq_opportunity_delivery"),
    )
    op.create_index("ix_opportunity_deliveries_brief_id", "opportunity_deliveries", ["brief_id"])


def downgrade():
    op.drop_column("brief_responses", "target_id")
    op.drop_column("brief_responses", "target_type")
    op.drop_table("opportunity_deliveries")
    op.drop_table("opportunity_filters")
    for column in (
        "public_requirements_json",
        "budget_max_rub",
        "budget_min_rub",
        "share_budget",
        "event_type",
    ):
        op.drop_column("public_briefs", column)
