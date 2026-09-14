"""Preferred participants for clean repeated events."""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("event_repeat_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("event_team_requirements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(16), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("hall_id", sa.String(36), nullable=True))
    op.create_index("ix_event_repeat_preferences_event_id", "event_repeat_preferences", ["event_id"])


def downgrade():
    op.drop_table("event_repeat_preferences")
