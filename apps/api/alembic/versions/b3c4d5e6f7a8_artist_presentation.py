"""Versioned artist presentation, with explicit media and technical facts."""
from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "artist_presentations",
        sa.Column("artist_id", sa.String(36), sa.ForeignKey("artists.id"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("artist_presentations")
