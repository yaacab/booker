"""Committed email worker claims and retry scheduling."""
from alembic import op
import sqlalchemy as sa

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('email_outbox', sa.Column('claim_token', sa.String(64), nullable=True))
    op.add_column('email_outbox', sa.Column('claim_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('email_outbox', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('email_outbox', 'next_attempt_at')
    op.drop_column('email_outbox', 'claim_expires_at')
    op.drop_column('email_outbox', 'claim_token')
