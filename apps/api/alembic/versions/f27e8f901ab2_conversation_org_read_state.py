"""Scope commercial conversation read state to the acting organization.

Revision ID: f27e8f901ab2
Revises: f16d7e8f901a
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f27e8f901ab2"
down_revision: str | None = "f16d7e8f901a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_party_scope() -> bool:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]: column
        for column in inspector.get_columns("conversation_read_states")
    }
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("conversation_read_states")
    }
    return (
        "organization_id" in columns
        and not columns["organization_id"]["nullable"]
        and ("conversation_id", "user_id", "organization_id") in unique_sets
        and ("conversation_id", "user_id") not in unique_sets
    )


def upgrade() -> None:
    if _has_party_scope():
        return
    if op.get_bind().dialect.name == "postgresql":
        _upgrade_postgresql()
        return
    op.create_table(
        "conversation_read_states_party",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("last_read_sequence", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "user_id",
            "organization_id",
            name="uq_conversation_read_state_party",
        ),
    )
    # Preserve a legacy read position only when current membership identifies exactly
    # one participant organization. Ambiguous dual-party positions are reset safely.
    op.execute(
        sa.text(
            "INSERT INTO conversation_read_states_party "
            "(id, conversation_id, user_id, organization_id, last_read_sequence, read_at) "
            "SELECT rs.id, rs.conversation_id, rs.user_id, MIN(tm.organization_id), "
            "rs.last_read_sequence, rs.read_at FROM conversation_read_states rs "
            "JOIN conversations c ON c.id = rs.conversation_id "
            "JOIN team_members tm ON tm.user_id = rs.user_id "
            "AND tm.organization_id IN (c.customer_org_id, c.supplier_org_id) "
            "GROUP BY rs.id, rs.conversation_id, rs.user_id, "
            "rs.last_read_sequence, rs.read_at "
            "HAVING COUNT(DISTINCT tm.organization_id) = 1"
        )
    )
    op.drop_table("conversation_read_states")
    op.rename_table("conversation_read_states_party", "conversation_read_states")
    op.create_index(
        "ix_conversation_read_states_conversation_id",
        "conversation_read_states",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_read_states_user_id", "conversation_read_states", ["user_id"]
    )
    op.create_index(
        "ix_conversation_read_states_organization_id",
        "conversation_read_states",
        ["organization_id"],
    )


def _upgrade_postgresql() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("conversation_read_states")
    }
    if "organization_id" not in columns:
        op.add_column(
            "conversation_read_states",
            sa.Column("organization_id", sa.String(length=36), nullable=True),
        )
    bind.execute(
        sa.text(
            "UPDATE conversation_read_states SET organization_id = NULL "
            "WHERE organization_id IS NOT NULL AND organization_id NOT IN ("
            "SELECT c.customer_org_id FROM conversations c "
            "WHERE c.id = conversation_read_states.conversation_id UNION ALL "
            "SELECT c.supplier_org_id FROM conversations c "
            "WHERE c.id = conversation_read_states.conversation_id)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE conversation_read_states rs SET organization_id = chosen.organization_id "
            "FROM (SELECT state.id, MIN(tm.organization_id) AS organization_id "
            "FROM conversation_read_states state "
            "JOIN conversations c ON c.id = state.conversation_id "
            "JOIN team_members tm ON tm.user_id = state.user_id "
            "AND tm.organization_id IN (c.customer_org_id, c.supplier_org_id) "
            "WHERE state.organization_id IS NULL GROUP BY state.id "
            "HAVING COUNT(DISTINCT tm.organization_id) = 1) chosen "
            "WHERE rs.id = chosen.id"
        )
    )
    bind.execute(
        sa.text("DELETE FROM conversation_read_states WHERE organization_id IS NULL")
    )
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("conversation_read_states"):
        if tuple(constraint.get("column_names") or ()) == ("conversation_id", "user_id"):
            op.drop_constraint(
                constraint["name"], "conversation_read_states", type_="unique"
            )
    foreign_keys = {
        tuple(fk.get("constrained_columns") or ())
        for fk in inspector.get_foreign_keys("conversation_read_states")
    }
    if ("organization_id",) not in foreign_keys:
        op.create_foreign_key(
            "fk_conversation_read_states_organization_id",
            "conversation_read_states",
            "organizations",
            ["organization_id"],
            ["id"],
        )
    op.alter_column(
        "conversation_read_states",
        "organization_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in sa.inspect(bind).get_unique_constraints("conversation_read_states")
    }
    if ("conversation_id", "user_id", "organization_id") not in unique_sets:
        op.create_unique_constraint(
            "uq_conversation_read_state_party",
            "conversation_read_states",
            ["conversation_id", "user_id", "organization_id"],
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("conversation_read_states")}
    if "ix_conversation_read_states_organization_id" not in indexes:
        op.create_index(
            "ix_conversation_read_states_organization_id",
            "conversation_read_states",
            ["organization_id"],
        )
    if "ix_conversation_read_states_user_id" not in indexes:
        op.create_index(
            "ix_conversation_read_states_user_id",
            "conversation_read_states",
            ["user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT conversation_id, user_id "
            "FROM conversation_read_states GROUP BY conversation_id, user_id "
            "HAVING COUNT(*) > 1) duplicate_states"
        )
    ).scalar_one()
    if duplicates:
        raise RuntimeError("Refusing to merge organization-scoped read states")
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            "uq_conversation_read_state_party",
            "conversation_read_states",
            type_="unique",
        )
        op.drop_index(
            "ix_conversation_read_states_organization_id",
            table_name="conversation_read_states",
        )
        foreign_keys = sa.inspect(bind).get_foreign_keys("conversation_read_states")
        for foreign_key in foreign_keys:
            if tuple(foreign_key.get("constrained_columns") or ()) == ("organization_id",):
                op.drop_constraint(
                    foreign_key["name"], "conversation_read_states", type_="foreignkey"
                )
        op.drop_column("conversation_read_states", "organization_id")
        op.create_unique_constraint(
            "uq_conversation_read_states_conversation_user",
            "conversation_read_states",
            ["conversation_id", "user_id"],
        )
        return
    op.create_table(
        "conversation_read_states_legacy",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("last_read_sequence", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO conversation_read_states_legacy "
            "(id, conversation_id, user_id, last_read_sequence, read_at) "
            "SELECT id, conversation_id, user_id, last_read_sequence, read_at "
            "FROM conversation_read_states"
        )
    )
    op.drop_table("conversation_read_states")
    op.rename_table("conversation_read_states_legacy", "conversation_read_states")
    op.create_index(
        "ix_conversation_read_states_conversation_id",
        "conversation_read_states",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_read_states_user_id", "conversation_read_states", ["user_id"]
    )
