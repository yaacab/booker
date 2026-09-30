"""Add acceptance deadlines without inventing deadlines for historical quotes."""
from alembic import op
import sqlalchemy as sa

revision = 'c6d7e8f9a0b1'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('offer_versions', sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('offer_versions', sa.Column('expiry_notified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_offer_versions_valid_until', 'offer_versions', ['valid_until'])


def downgrade():
    op.drop_index('ix_offer_versions_valid_until', table_name='offer_versions')
    op.drop_column('offer_versions', 'expiry_notified_at')
    op.drop_column('offer_versions', 'valid_until')
