"""Bind verified provider events and references to one payment."""
from alembic import op
import sqlalchemy as sa

revision = 'f9a0b1c2d3e4'
down_revision = 'e8f9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payment_webhook_events', sa.Column('event_fingerprint', sa.String(64), nullable=True))
    op.create_index('uq_payment_provider_reference', 'payments', ['provider', 'provider_reference'], unique=True)


def downgrade():
    op.drop_index('uq_payment_provider_reference', table_name='payments')
    op.drop_column('payment_webhook_events', 'event_fingerprint')
