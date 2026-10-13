"""Track explicit operator acceptance independently from ticket assignment.

Revision ID: a06f78d90e12
Revises: a05f67c89d01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a06f78d90e12"
down_revision: str | None = "a05f67c89d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCEPTANCE_CHECK = (
    "(accepted_by_user_id IS NULL AND accepted_at IS NULL) OR "
    "(accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL "
    "AND assigned_to_user_id IS NOT NULL "
    "AND accepted_by_user_id = assigned_to_user_id)"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("support_tickets")}
    if "accepted_by_user_id" not in columns:
        op.add_column("support_tickets", sa.Column(
            "accepted_by_user_id", sa.String(36), nullable=True,
        ))
    if "accepted_at" not in columns:
        op.add_column("support_tickets", sa.Column(
            "accepted_at", sa.DateTime(timezone=True), nullable=True,
        ))
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("support_tickets")}
    if not {"assigned_to_user_id", "accepted_by_user_id", "accepted_at"} <= columns:
        raise RuntimeError("support acceptance columns require schema review")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS support_ticket_acceptance_insert")
        op.execute("DROP TRIGGER IF EXISTS support_ticket_acceptance_update")
        for event in ("INSERT", "UPDATE"):
            op.execute(
                f"CREATE TRIGGER support_ticket_acceptance_{event.lower()} "
                f"BEFORE {event} ON support_tickets "
                f"WHEN NOT ({_ACCEPTANCE_CHECK.replace('accepted_', 'NEW.accepted_').replace('assigned_to_user_id', 'NEW.assigned_to_user_id')}) "
                "BEGIN SELECT RAISE(ABORT, 'support acceptance inconsistent'); END"
            )
    elif bind.dialect.name == "postgresql":
        foreign_keys = inspector.get_foreign_keys("support_tickets")
        if not any(
            fk.get("constrained_columns") == ["accepted_by_user_id"]
            and fk.get("referred_table") == "users"
            and fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        ):
            op.create_foreign_key(
                "fk_support_ticket_accepted_by", "support_tickets", "users",
                ["accepted_by_user_id"], ["id"],
            )
        checks = {check.get("name") for check in inspector.get_check_constraints("support_tickets")}
        if "ck_support_ticket_acceptance" not in checks:
            op.create_check_constraint(
                "ck_support_ticket_acceptance", "support_tickets", _ACCEPTANCE_CHECK,
            )


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing support acceptance evidence")
