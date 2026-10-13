"""Start conversations at the addressable request stage.

Revision ID: e7a8b9c0d1e2
Revises: d6f7a8b9c0d1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7a8b9c0d1e2"
down_revision: str | None = "d6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("request_id", sa.String(length=36), nullable=True))
    op.execute(
        sa.text(
            "UPDATE conversations SET request_id = ("
            "SELECT o.request_id FROM bookings b JOIN offers o ON o.id = b.offer_id "
            "WHERE b.id = conversations.booking_id)"
        )
    )
    with op.batch_alter_table("conversations") as batch:
        batch.alter_column("booking_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_foreign_key(
            "fk_conversations_request_id_requests", "requests", ["request_id"], ["id"]
        )
        batch.create_unique_constraint("uq_conversations_request_id", ["request_id"])

    op.add_column(
        "messages", sa.Column("idempotency_key", sa.String(length=64), nullable=True)
    )
    has_key = sa.text("idempotency_key IS NOT NULL")
    op.create_index(
        "uq_message_conversation_idempotency",
        "messages",
        ["conversation_id", "idempotency_key"],
        unique=True,
        sqlite_where=has_key,
        postgresql_where=has_key,
    )
    op.create_table(
        "conversation_read_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id"),
    )
    op.create_index(
        "ix_conversation_read_states_conversation_id",
        "conversation_read_states",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_read_states_user_id", "conversation_read_states", ["user_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT COUNT(*) FROM conversations WHERE booking_id IS NULL")
    ).scalar_one():
        raise RuntimeError("Refusing to drop request-stage conversations without bookings")
    op.drop_index("ix_conversation_read_states_user_id", table_name="conversation_read_states")
    op.drop_index(
        "ix_conversation_read_states_conversation_id", table_name="conversation_read_states"
    )
    op.drop_table("conversation_read_states")
    op.drop_index("uq_message_conversation_idempotency", table_name="messages")
    op.drop_column("messages", "idempotency_key")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("uq_conversations_request_id", type_="unique")
        batch.drop_constraint("fk_conversations_request_id_requests", type_="foreignkey")
        batch.alter_column("booking_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("request_id")
