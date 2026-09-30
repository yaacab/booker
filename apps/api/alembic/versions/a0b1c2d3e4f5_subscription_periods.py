"""Persist subscription agreement periods and unique provider payment references."""
from alembic import op
import sqlalchemy as sa

revision = 'a0b1c2d3e4f5'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('subscriptions', sa.Column('agreement_order_id', sa.String(36), nullable=True))
    op.add_column('billing_orders', sa.Column('subscription_parent_id', sa.String(36), nullable=True))
    op.add_column('billing_orders', sa.Column('period_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('billing_orders', sa.Column('period_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('billing_orders', sa.Column('entitlement_eligible', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index('uq_billing_provider_reference', 'billing_orders', ['provider', 'provider_reference'], unique=True)
    op.create_index('uq_billing_subscription_period', 'billing_orders', ['subscription_parent_id', 'period_start'], unique=True)


def downgrade():
    op.drop_index('uq_billing_subscription_period', table_name='billing_orders')
    op.drop_index('uq_billing_provider_reference', table_name='billing_orders')
    for column in ('entitlement_eligible', 'period_end', 'period_start', 'subscription_parent_id'):
        op.drop_column('billing_orders', column)
    op.drop_column('subscriptions', 'agreement_order_id')
