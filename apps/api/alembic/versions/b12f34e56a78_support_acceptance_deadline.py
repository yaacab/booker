"""Durable acceptance escalation marker, separate from first-response SLA."""
from alembic import op
import sqlalchemy as sa

revision = "b12f34e56a78"
down_revision = "a11f23e45f67"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {row["name"] for row in sa.inspect(bind).get_columns("support_tickets")}
    if "acceptance_escalated_at" not in columns:
        op.add_column("support_tickets", sa.Column(
            "acceptance_escalated_at", sa.DateTime(timezone=True), nullable=True,
        ))


def downgrade():
    raise RuntimeError("manual migration required before removing acceptance escalation evidence")
