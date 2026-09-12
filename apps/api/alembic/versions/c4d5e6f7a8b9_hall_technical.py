"""Versioned hall technical facts for explainable compatibility."""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hall_technical_profiles",
        sa.Column("hall_id", sa.String(36), sa.ForeignKey("venue_halls.id"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("hall_technical_profiles")
