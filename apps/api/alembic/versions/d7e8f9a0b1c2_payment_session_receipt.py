"""Persist booking checkout receipts and recovery state."""
from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payments", sa.Column("checkout_url", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("provider_reference", sa.String(255), nullable=True))
    # Existing payments must never trigger a new provider session on replay.
    op.add_column("payments", sa.Column("session_state", sa.String(24), server_default="ready", nullable=False))


def downgrade():
    op.drop_column("payments", "session_state")
    op.drop_column("payments", "provider_reference")
    op.drop_column("payments", "checkout_url")
