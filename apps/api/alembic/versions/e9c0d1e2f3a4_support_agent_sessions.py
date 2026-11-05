"""Add bounded support assistant sessions, exchanges, feedback, and escalation link.

Revision ID: e9c0d1e2f3a4
Revises: e8b9c0d1e2f3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9c0d1e2f3a4"
down_revision: str | None = "e8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    managed_tables = {
        "support_agent_sessions": {
            "id",
            "user_id",
            "organization_id",
            "related_type",
            "related_id",
            "status",
            "ticket_id",
            "idempotency_key_hash",
            "request_fingerprint",
            "escalation_idempotency_key_hash",
            "escalation_request_fingerprint",
            "created_at",
            "updated_at",
            "escalated_at",
        },
        "support_agent_exchanges": {
            "id",
            "session_id",
            "user_message",
            "assistant_message",
            "intent",
            "outcome",
            "needs_human",
            "source_ids_json",
            "idempotency_key_hash",
            "request_fingerprint",
            "created_at",
        },
        "support_agent_feedback": {
            "id",
            "exchange_id",
            "user_id",
            "rating",
            "reason_code",
            "comment",
            "created_at",
        },
    }
    existing_tables = set(inspector.get_table_names())
    present = existing_tables.intersection(managed_tables)
    if present:
        if present != set(managed_tables):
            raise RuntimeError("Refusing to adopt a partial support-agent schema")
        required_uniques = {
            "support_agent_sessions": {
                frozenset({"ticket_id"}),
                frozenset({"user_id", "idempotency_key_hash"}),
            },
            "support_agent_exchanges": {
                frozenset({"session_id", "idempotency_key_hash"}),
            },
            "support_agent_feedback": {frozenset({"exchange_id", "user_id"})},
        }
        required_checks = {
            "support_agent_sessions": {
                "ck_support_agent_session_status",
                "ck_support_agent_session_escalation_state",
            },
            "support_agent_exchanges": {
                "ck_support_agent_exchange_outcome",
                "ck_support_agent_exchange_handoff",
            },
            "support_agent_feedback": {"ck_support_agent_feedback_rating"},
        }
        required_fks = {
            "support_agent_sessions": {
                ("user_id", "users"),
                ("organization_id", "organizations"),
                ("ticket_id", "support_tickets"),
            },
            "support_agent_exchanges": {("session_id", "support_agent_sessions")},
            "support_agent_feedback": {
                ("exchange_id", "support_agent_exchanges"),
                ("user_id", "users"),
            },
        }
        for table, expected_columns in managed_tables.items():
            actual_columns = {item["name"] for item in inspector.get_columns(table)}
            if not expected_columns.issubset(actual_columns):
                raise RuntimeError(f"Refusing to adopt an incompatible {table} table")
            uniques = {
                frozenset(item.get("column_names") or [])
                for item in inspector.get_unique_constraints(table)
            }
            checks = {item.get("name") for item in inspector.get_check_constraints(table)}
            fks = {
                (item["constrained_columns"][0], item["referred_table"])
                for item in inspector.get_foreign_keys(table)
                if len(item["constrained_columns"]) == 1
            }
            if (
                not required_uniques[table].issubset(uniques)
                or not required_checks[table].issubset(checks)
                or not required_fks[table].issubset(fks)
            ):
                raise RuntimeError(f"Refusing to adopt an incompatible {table} table")
        # Pilot SQLite may have created the current model schema before Alembic owned it.
        # The validated tables can be adopted safely by advancing this revision.
        return

    op.create_table(
        "support_agent_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("related_type", sa.String(length=32), nullable=True),
        sa.Column("related_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("escalation_idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("escalation_request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'escalated', 'closed')",
            name="ck_support_agent_session_status",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND ticket_id IS NULL AND escalated_at IS NULL) OR "
            "(status = 'escalated' AND ticket_id IS NOT NULL AND escalated_at IS NOT NULL) OR "
            "status = 'closed'",
            name="ck_support_agent_session_escalation_state",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key_hash",
            name="uq_support_agent_session_user_idempotency",
        ),
    )
    op.create_index(
        "ix_support_agent_sessions_user_id", "support_agent_sessions", ["user_id"]
    )
    op.create_index(
        "ix_support_agent_sessions_organization_id",
        "support_agent_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_support_agent_sessions_related_id", "support_agent_sessions", ["related_id"]
    )
    op.create_index(
        "ix_support_agent_sessions_status", "support_agent_sessions", ["status"]
    )

    op.create_table(
        "support_agent_exchanges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("assistant_message", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("needs_human", sa.Boolean(), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('answered', 'clarify', 'needs_human')",
            name="ck_support_agent_exchange_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'needs_human' AND needs_human = true) OR "
            "(outcome != 'needs_human' AND needs_human = false)",
            name="ck_support_agent_exchange_handoff",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["support_agent_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "idempotency_key_hash",
            name="uq_support_agent_exchange_session_idempotency",
        ),
    )
    op.create_index(
        "ix_support_agent_exchanges_session_id", "support_agent_exchanges", ["session_id"]
    )
    op.create_index(
        "ix_support_agent_exchanges_intent", "support_agent_exchanges", ["intent"]
    )
    op.create_index(
        "ix_support_agent_exchanges_outcome", "support_agent_exchanges", ["outcome"]
    )

    op.create_table(
        "support_agent_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("exchange_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rating IN ('helpful', 'not_helpful')",
            name="ck_support_agent_feedback_rating",
        ),
        sa.ForeignKeyConstraint(["exchange_id"], ["support_agent_exchanges.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "exchange_id", "user_id", name="uq_support_agent_feedback_exchange_user"
        ),
    )
    op.create_index(
        "ix_support_agent_feedback_exchange_id", "support_agent_feedback", ["exchange_id"]
    )
    op.create_index(
        "ix_support_agent_feedback_user_id", "support_agent_feedback", ["user_id"]
    )

def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table in (
        "support_agent_feedback",
        "support_agent_exchanges",
        "support_agent_sessions",
    ):
        if table in tables and bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError(f"Refusing to drop non-empty {table}; export support history first")
    op.drop_index("ix_support_agent_feedback_user_id", table_name="support_agent_feedback")
    op.drop_index("ix_support_agent_feedback_exchange_id", table_name="support_agent_feedback")
    op.drop_table("support_agent_feedback")
    op.drop_index("ix_support_agent_exchanges_outcome", table_name="support_agent_exchanges")
    op.drop_index("ix_support_agent_exchanges_intent", table_name="support_agent_exchanges")
    op.drop_index("ix_support_agent_exchanges_session_id", table_name="support_agent_exchanges")
    op.drop_table("support_agent_exchanges")
    op.drop_index("ix_support_agent_sessions_status", table_name="support_agent_sessions")
    op.drop_index("ix_support_agent_sessions_related_id", table_name="support_agent_sessions")
    op.drop_index(
        "ix_support_agent_sessions_organization_id", table_name="support_agent_sessions"
    )
    op.drop_index("ix_support_agent_sessions_user_id", table_name="support_agent_sessions")
    op.drop_table("support_agent_sessions")
