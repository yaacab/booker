"""Add isolated support messages, operator notes, idempotency, and CAS state.

Revision ID: e8b9c0d1e2f3
Revises: e7a8b9c0d1e2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8b9c0d1e2f3"
down_revision: str | None = "e7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    ticket_columns = {item["name"] for item in inspector.get_columns("support_tickets")}
    expected_ticket_columns = {
        "state_version",
        "idempotency_key_hash",
        "request_fingerprint",
        "closed_at",
        "closed_by_user_id",
        "reopened_at",
    }
    expected_tables = {"support_messages", "support_operator_notes"}
    existing_tables = set(inspector.get_table_names())
    already_adopted = expected_ticket_columns.issubset(ticket_columns) and expected_tables.issubset(
        existing_tables
    )
    if already_adopted:
        ticket_uniques = {
            frozenset(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("support_tickets")
        }
        ticket_fks = {
            (item["constrained_columns"][0], item["referred_table"])
            for item in inspector.get_foreign_keys("support_tickets")
            if len(item["constrained_columns"]) == 1
        }
        missing_ticket_unique = frozenset({"author_user_id", "idempotency_key_hash"}) not in ticket_uniques
        missing_closed_by_fk = ("closed_by_user_id", "users") not in ticket_fks
        if missing_ticket_unique or missing_closed_by_fk:
            # Pilot SQLite created these columns before Alembic owned the constraints.
            # Batch rebuild preserves rows and fails if duplicates/orphans prevent repair.
            with op.batch_alter_table("support_tickets") as batch:
                if missing_ticket_unique:
                    batch.create_unique_constraint(
                        "uq_support_ticket_author_idempotency",
                        ["author_user_id", "idempotency_key_hash"],
                    )
                if missing_closed_by_fk:
                    batch.create_foreign_key(
                        "fk_support_tickets_closed_by_user_id_users",
                        "users",
                        ["closed_by_user_id"],
                        ["id"],
                    )
            inspector = sa.inspect(op.get_bind())
        required_columns = {
            "support_tickets": expected_ticket_columns,
            "support_messages": {
                "id", "ticket_id", "author_user_id", "author_kind", "body",
                "idempotency_key_hash", "request_fingerprint", "created_at",
            },
            "support_operator_notes": {
                "id", "ticket_id", "author_user_id", "body",
                "idempotency_key_hash", "request_fingerprint", "created_at",
            },
        }
        required_uniques = {
            "support_tickets": {frozenset({"author_user_id", "idempotency_key_hash"})},
            "support_messages": {
                frozenset({"ticket_id", "author_user_id", "idempotency_key_hash"})
            },
            "support_operator_notes": {
                frozenset({"ticket_id", "author_user_id", "idempotency_key_hash"})
            },
        }
        required_fks = {
            "support_tickets": {("closed_by_user_id", "users")},
            "support_messages": {
                ("ticket_id", "support_tickets"), ("author_user_id", "users")
            },
            "support_operator_notes": {
                ("ticket_id", "support_tickets"), ("author_user_id", "users")
            },
        }
        for table, expected_columns in required_columns.items():
            columns = {item["name"] for item in inspector.get_columns(table)}
            uniques = {
                frozenset(item.get("column_names") or [])
                for item in inspector.get_unique_constraints(table)
            }
            fks = {
                (item["constrained_columns"][0], item["referred_table"])
                for item in inspector.get_foreign_keys(table)
                if len(item["constrained_columns"]) == 1
            }
            if (
                not expected_columns.issubset(columns)
                or not required_uniques[table].issubset(uniques)
                or not required_fks[table].issubset(fks)
                or (
                    table == "support_messages"
                    and "ck_support_message_author_kind"
                    not in {item.get("name") for item in inspector.get_check_constraints(table)}
                )
            ):
                raise RuntimeError(f"Refusing to adopt an incompatible {table} table")
        return
    if expected_ticket_columns.intersection(ticket_columns) or expected_tables.intersection(
        existing_tables
    ):
        raise RuntimeError("Refusing to adopt a partial support-ticket schema")

    op.add_column(
        "support_tickets",
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "support_tickets",
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column("closed_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("support_tickets") as batch:
        batch.create_foreign_key(
            "fk_support_tickets_closed_by_user_id_users",
            "users",
            ["closed_by_user_id"],
            ["id"],
        )
        batch.create_unique_constraint(
            "uq_support_ticket_author_idempotency",
            ["author_user_id", "idempotency_key_hash"],
        )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("author_kind", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "author_kind IN ('user', 'operator')",
            name="ck_support_message_author_kind",
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticket_id",
            "author_user_id",
            "idempotency_key_hash",
            name="uq_support_message_actor_idempotency",
        ),
    )
    op.create_index(
        "ix_support_messages_ticket_id", "support_messages", ["ticket_id"]
    )
    op.create_index(
        "ix_support_messages_author_user_id", "support_messages", ["author_user_id"]
    )

    op.create_table(
        "support_operator_notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticket_id",
            "author_user_id",
            "idempotency_key_hash",
            name="uq_support_note_actor_idempotency",
        ),
    )
    op.create_index(
        "ix_support_operator_notes_ticket_id",
        "support_operator_notes",
        ["ticket_id"],
    )
    op.create_index(
        "ix_support_operator_notes_author_user_id",
        "support_operator_notes",
        ["author_user_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table in ("support_messages", "support_operator_notes"):
        if table in tables and bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError(f"Refusing to drop non-empty {table}; export support history first")
    op.drop_index(
        "ix_support_operator_notes_author_user_id",
        table_name="support_operator_notes",
    )
    op.drop_index(
        "ix_support_operator_notes_ticket_id", table_name="support_operator_notes"
    )
    op.drop_table("support_operator_notes")
    op.drop_index("ix_support_messages_author_user_id", table_name="support_messages")
    op.drop_index("ix_support_messages_ticket_id", table_name="support_messages")
    op.drop_table("support_messages")
    with op.batch_alter_table("support_tickets") as batch:
        batch.drop_constraint("uq_support_ticket_author_idempotency", type_="unique")
        batch.drop_constraint(
            "fk_support_tickets_closed_by_user_id_users", type_="foreignkey"
        )
    op.drop_column("support_tickets", "reopened_at")
    op.drop_column("support_tickets", "closed_by_user_id")
    op.drop_column("support_tickets", "closed_at")
    op.drop_column("support_tickets", "request_fingerprint")
    op.drop_column("support_tickets", "idempotency_key_hash")
    op.drop_column("support_tickets", "state_version")
