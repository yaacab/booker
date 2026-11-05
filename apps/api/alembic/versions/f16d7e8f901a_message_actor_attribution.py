"""Attribute commercial chat messages to immutable deal participants.

Revision ID: f16d7e8f901a
Revises: f05c6d7e8f90
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f16d7e8f901a"
down_revision: str | None = "f05c6d7e8f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("messages")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("messages")}
    checks = {check["name"] for check in inspector.get_check_constraints("messages")}
    with op.batch_alter_table("messages") as batch:
        if "author_org_id" not in columns:
            batch.add_column(sa.Column("author_org_id", sa.String(length=36), nullable=True))
        if "fk_messages_author_org_id_organizations" not in foreign_keys:
            batch.create_foreign_key(
                "fk_messages_author_org_id_organizations",
                "organizations",
                ["author_org_id"],
                ["id"],
            )
        if "author_side" not in columns:
            batch.add_column(sa.Column("author_side", sa.String(length=16), nullable=True))
        if "author_name_snapshot" not in columns:
            batch.add_column(
                sa.Column("author_name_snapshot", sa.String(length=255), nullable=True)
            )
        if "actor_role_snapshot" not in columns:
            batch.add_column(
                sa.Column("actor_role_snapshot", sa.String(length=32), nullable=True)
            )
        if "attribution_status" not in columns:
            batch.add_column(
                sa.Column(
                    "attribution_status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="legacy_unattributed",
                )
            )
        if "ck_message_actor_attribution" not in checks:
            batch.create_check_constraint(
                "ck_message_actor_attribution",
                "(attribution_status = 'system' AND kind = 'system' "
                "AND author_user_id IS NULL AND author_org_id IS NULL "
                "AND author_side IS NULL AND author_name_snapshot IS NULL "
                "AND actor_role_snapshot IS NULL) OR "
                "(attribution_status = 'legacy_unattributed' AND author_org_id IS NULL "
                "AND author_side IS NULL) OR "
                "(attribution_status = 'attributed' AND kind = 'chat' "
                "AND author_user_id IS NOT NULL AND author_org_id IS NOT NULL "
                "AND author_side IN ('customer', 'supplier') "
                "AND author_name_snapshot IS NOT NULL "
                "AND actor_role_snapshot IS NOT NULL)",
            )
    op.execute(
        sa.text(
            "UPDATE messages SET attribution_status = 'system' WHERE kind = 'system'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("ck_message_actor_attribution", type_="check")
        batch.drop_constraint(
            "fk_messages_author_org_id_organizations", type_="foreignkey"
        )
        batch.drop_column("attribution_status")
        batch.drop_column("author_name_snapshot")
        batch.drop_column("actor_role_snapshot")
        batch.drop_column("author_side")
        batch.drop_column("author_org_id")
