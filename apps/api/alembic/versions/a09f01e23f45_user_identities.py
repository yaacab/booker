"""Add external identity bindings without changing existing Booker accounts.

Revision ID: a09f01e23f45
Revises: a08f90e12f34
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a09f01e23f45"
down_revision: str | None = "a08f90e12f34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = {
    "id", "user_id", "provider", "provider_subject", "provider_email",
    "provider_email_verified", "provider_phone", "link_origin", "linked_at",
    "last_login_at",
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError("External identity migration requires reviewed database engine")
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_identities"):
        op.create_table(
            "user_identities",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider", sa.String(16), nullable=False),
            sa.Column("provider_subject", sa.String(255), nullable=False),
            sa.Column("provider_email", sa.String(255), nullable=True),
            sa.Column("provider_email_verified", sa.Boolean(), nullable=True),
            sa.Column("provider_phone", sa.String(32), nullable=True),
            sa.Column("link_origin", sa.String(16), nullable=False),
            sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("provider", "provider_subject", name="uq_user_identity_subject"),
            sa.UniqueConstraint("user_id", "provider", name="uq_user_identity_user_provider"),
            sa.CheckConstraint("provider IN ('telegram','yandex','vk')",
                               name="ck_user_identity_provider"),
            sa.CheckConstraint("length(provider_subject) > 0",
                               name="ck_user_identity_subject"),
            sa.CheckConstraint("link_origin IN ('first_login','explicit_link')",
                               name="ck_user_identity_link_origin"),
        )
        op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
        inspector = sa.inspect(bind)

    columns = {row["name"]: row for row in inspector.get_columns("user_identities")}
    unique_sets = {
        tuple(row.get("column_names") or ())
        for row in inspector.get_unique_constraints("user_identities")
    }
    foreign_keys = inspector.get_foreign_keys("user_identities")
    checks = {row.get("name") for row in inspector.get_check_constraints("user_identities")}
    indexes = {row.get("name") for row in inspector.get_indexes("user_identities")}
    if (
        set(columns) != _COLUMNS
        or inspector.get_pk_constraint("user_identities").get("constrained_columns") != ["id"]
        or any(columns[name]["nullable"] for name in (
            "id", "user_id", "provider", "provider_subject", "link_origin", "linked_at"
        ))
        or ("provider", "provider_subject") not in unique_sets
        or ("user_id", "provider") not in unique_sets
        or not any(
            fk.get("constrained_columns") == ["user_id"]
            and fk.get("referred_table") == "users"
            and fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
        or not {"ck_user_identity_provider", "ck_user_identity_subject",
                "ck_user_identity_link_origin"} <= checks
        or "ix_user_identities_user_id" not in indexes
    ):
        raise RuntimeError("Existing external identity table requires schema review")


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing identity links")
