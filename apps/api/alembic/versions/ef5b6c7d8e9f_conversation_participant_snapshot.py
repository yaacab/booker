"""Snapshot conversation participant organizations.

Revision ID: ef5b6c7d8e9f
Revises: ed4a5b6c7d8e
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ef5b6c7d8e9f"
down_revision: str | None = "ed4a5b6c7d8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns("conversations")}


def _foreign_keys() -> dict[tuple[str, ...], str | None]:
    return {
        tuple(item["constrained_columns"]): item.get("name")
        for item in sa.inspect(op.get_bind()).get_foreign_keys("conversations")
    }


def upgrade() -> None:
    columns = _columns()
    if "customer_org_id" not in columns:
        op.add_column(
            "conversations", sa.Column("customer_org_id", sa.String(length=36), nullable=True)
        )
    if "supplier_org_id" not in columns:
        op.add_column(
            "conversations", sa.Column("supplier_org_id", sa.String(length=36), nullable=True)
        )
    if "customer_name_snapshot" not in columns:
        op.add_column(
            "conversations",
            sa.Column("customer_name_snapshot", sa.String(length=255), nullable=True),
        )
    if "supplier_name_snapshot" not in columns:
        op.add_column(
            "conversations",
            sa.Column("supplier_name_snapshot", sa.String(length=255), nullable=True),
        )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE conversations SET customer_org_id = COALESCE(customer_org_id, ("
            "SELECT e.organization_id FROM requests r JOIN events e ON e.id = r.event_id "
            "WHERE r.id = conversations.request_id)), supplier_org_id = COALESCE(supplier_org_id, ("
            "SELECT r.supplier_org_id FROM requests r "
            "WHERE r.id = conversations.request_id)), customer_name_snapshot = "
            "COALESCE(customer_name_snapshot, ("
            "SELECT o.name FROM organizations o JOIN events e ON e.organization_id = o.id "
            "JOIN requests r ON r.event_id = e.id WHERE r.id = conversations.request_id)), "
            "supplier_name_snapshot = COALESCE(supplier_name_snapshot, ("
            "SELECT o.name FROM organizations o JOIN requests r "
            "ON r.supplier_org_id = o.id WHERE r.id = conversations.request_id))"
        )
    )
    missing = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM conversations "
            "WHERE customer_org_id IS NULL OR supplier_org_id IS NULL "
            "OR customer_name_snapshot IS NULL OR supplier_name_snapshot IS NULL"
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Cannot snapshot conversation participants: request or event relation is missing"
        )
    foreign_keys = _foreign_keys()
    with op.batch_alter_table("conversations") as batch:
        batch.alter_column(
            "customer_org_id", existing_type=sa.String(length=36), nullable=False
        )
        batch.alter_column(
            "supplier_org_id", existing_type=sa.String(length=36), nullable=False
        )
        batch.alter_column(
            "customer_name_snapshot", existing_type=sa.String(length=255), nullable=False
        )
        batch.alter_column(
            "supplier_name_snapshot", existing_type=sa.String(length=255), nullable=False
        )
        if ("customer_org_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_conversations_customer_org_id_organizations",
                "organizations",
                ["customer_org_id"],
                ["id"],
            )
        if ("supplier_org_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_conversations_supplier_org_id_organizations",
                "organizations",
                ["supplier_org_id"],
                ["id"],
            )


def downgrade() -> None:
    changed = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM conversations c "
            "JOIN requests r ON r.id = c.request_id "
            "JOIN events e ON e.id = r.event_id "
            "WHERE c.customer_org_id <> e.organization_id "
            "OR c.supplier_org_id <> r.supplier_org_id "
            "OR c.customer_name_snapshot <> ("
            "SELECT name FROM organizations WHERE id = c.customer_org_id) "
            "OR c.supplier_name_snapshot <> ("
            "SELECT name FROM organizations WHERE id = c.supplier_org_id)"
        )
    ).scalar_one()
    if changed:
        raise RuntimeError("Refusing to discard historical conversation participant snapshots")
    foreign_keys = _foreign_keys()
    with op.batch_alter_table("conversations") as batch:
        supplier_fk = foreign_keys.get(("supplier_org_id",))
        customer_fk = foreign_keys.get(("customer_org_id",))
        if supplier_fk:
            batch.drop_constraint(supplier_fk, type_="foreignkey")
        if customer_fk:
            batch.drop_constraint(customer_fk, type_="foreignkey")
        batch.drop_column("supplier_name_snapshot")
        batch.drop_column("customer_name_snapshot")
        batch.drop_column("supplier_org_id")
        batch.drop_column("customer_org_id")
