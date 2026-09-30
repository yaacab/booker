"""Event end/type and durable scoped command receipts."""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("event_type", sa.String(128), nullable=False, server_default=""))
    op.create_table("event_command_receipts",
        sa.Column("scope", sa.String(128), primary_key=True),
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("event_command_receipts")
    op.drop_column("events", "event_type")
    op.drop_column("events", "ends_at")
