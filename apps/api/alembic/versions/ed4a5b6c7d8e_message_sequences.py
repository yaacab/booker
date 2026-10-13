"""Add monotonic conversation message and read positions.

Revision ID: ed4a5b6c7d8e
Revises: ec3f4a5b6c7d
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ed4a5b6c7d8e"
down_revision: str | None = "ec3f4a5b6c7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if "next_message_sequence" not in _columns("conversations"):
        op.add_column(
            "conversations",
            sa.Column(
                "next_message_sequence", sa.Integer(), server_default="1", nullable=False
            ),
        )
    if "sequence" not in _columns("messages"):
        op.add_column("messages", sa.Column("sequence", sa.Integer(), nullable=True))
    if "last_read_sequence" not in _columns("conversation_read_states"):
        op.add_column(
            "conversation_read_states",
            sa.Column("last_read_sequence", sa.Integer(), server_default="0", nullable=False),
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "WITH ranked AS ("
            "SELECT id, ROW_NUMBER() OVER (PARTITION BY conversation_id "
            "ORDER BY created_at, id) AS seq FROM messages"
            ") UPDATE messages SET sequence = ("
            "SELECT ranked.seq FROM ranked WHERE ranked.id = messages.id"
            ") WHERE sequence IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE conversations SET next_message_sequence = COALESCE(("
            "SELECT MAX(messages.sequence) + 1 FROM messages "
            "WHERE messages.conversation_id = conversations.id"
            "), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE conversation_read_states SET last_read_sequence = COALESCE(("
            "SELECT MAX(messages.sequence) FROM messages "
            "WHERE messages.conversation_id = conversation_read_states.conversation_id "
            "AND messages.created_at <= conversation_read_states.read_at"
            "), 0)"
        )
    )
    indexes = _indexes("messages")
    if "uq_messages_conversation_sequence" not in indexes:
        op.create_index(
            "uq_messages_conversation_sequence",
            "messages",
            ["conversation_id", "sequence"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM messages")).scalar_one():
        raise RuntimeError("Refusing to drop populated message sequence data")
    op.drop_index("uq_messages_conversation_sequence", table_name="messages")
    op.drop_column("conversation_read_states", "last_read_sequence")
    op.drop_column("messages", "sequence")
    op.drop_column("conversations", "next_message_sequence")
