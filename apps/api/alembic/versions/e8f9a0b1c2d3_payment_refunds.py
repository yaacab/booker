"""Durable refund requests and independent operator approval."""
from alembic import op
import sqlalchemy as sa

revision = 'e8f9a0b1c2d3'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_refunds',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payment_id', sa.String(36), sa.ForeignKey('payments.id'), nullable=False),
        sa.Column('amount_rub', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=False, unique=True),
        sa.Column('requested_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('provider_reference', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('provider', 'provider_reference', name='uq_refund_provider_reference'),
        sa.CheckConstraint('amount_rub > 0'),
        sa.CheckConstraint('approved_by IS NULL OR approved_by != requested_by'),
        sa.CheckConstraint("status IN ('awaiting_approval','approved','submitting','pending','uncertain','succeeded','failed','rejected')"))
    op.create_index('ix_payment_refunds_payment_id', 'payment_refunds', ['payment_id'])
    op.create_index('ix_payment_refunds_status', 'payment_refunds', ['status'])


def downgrade():
    op.drop_table('payment_refunds')
