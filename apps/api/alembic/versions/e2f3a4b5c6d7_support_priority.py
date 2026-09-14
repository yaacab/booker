"""Priority snapshot and retry-safe support submissions."""
from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("support_tickets", sa.Column("priority", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("support_tickets", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.add_column("support_tickets", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_index("ix_support_tickets_priority", "support_tickets", ["priority"])
    op.create_index("uq_support_ticket_idempotency", "support_tickets", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("uq_support_ticket_idempotency", table_name="support_tickets")
    op.drop_index("ix_support_tickets_priority", table_name="support_tickets")
    op.drop_column("support_tickets", "request_fingerprint")
    op.drop_column("support_tickets", "idempotency_key")
    op.drop_column("support_tickets", "priority")
