"""Scoped guest feedback for explicitly collaborative shortlists."""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shared_shortlists") as batch:
        batch.add_column(sa.Column("event_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_shortlist_event", "events", ["event_id"], ["id"])
        batch.create_index("ix_shared_shortlists_event_id", ["event_id"])
        batch.add_column(sa.Column("collaborative", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("shortlist_guests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shortlist_id", sa.String(36), sa.ForeignKey("shared_shortlists.id"), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("shortlist_id", "secret_hash"))
    op.create_index("ix_shortlist_guests_shortlist_id", "shortlist_guests", ["shortlist_id"])
    op.create_table("shortlist_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guest_id", sa.String(36), sa.ForeignKey("shortlist_guests.id"), nullable=False),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("shared_shortlist_items.id"), nullable=False),
        sa.Column("reaction", sa.String(16), nullable=True),
        sa.Column("comment", sa.String(1000), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("guest_id", "item_id"))
    op.create_index("ix_shortlist_feedback_guest_id", "shortlist_feedback", ["guest_id"])
    op.create_index("ix_shortlist_feedback_item_id", "shortlist_feedback", ["item_id"])


def downgrade():
    op.drop_table("shortlist_feedback")
    op.drop_table("shortlist_guests")
    with op.batch_alter_table("shared_shortlists") as batch:
        batch.drop_index("ix_shared_shortlists_event_id")
        batch.drop_constraint("fk_shortlist_event", type_="foreignkey")
        batch.drop_column("event_id")
        batch.drop_column("collaborative")
