"""Persist one-use external first-factor claims without bearer credentials.

Revision ID: a11f23e45f67
Revises: a10f12e34f56
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a11f23e45f67"
down_revision: str | None = "a10f12e34f56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError("Pending auth migration requires reviewed database engine")
    inspector = sa.inspect(bind)
    if not inspector.has_table("pending_external_auth"):
        op.create_table(
            "pending_external_auth",
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("provider", sa.String(16), nullable=False),
            sa.Column("provider_subject", sa.String(255), nullable=False),
            sa.Column("proof_hash", sa.String(64), nullable=False),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("provider", "proof_hash", name="uq_pending_external_auth_proof"),
            sa.CheckConstraint("provider IN ('telegram','yandex','vk')",
                               name="ck_pending_external_provider"),
        )
        op.create_index("ix_pending_external_auth_expires_at", "pending_external_auth",
                        ["expires_at"])
        inspector = sa.inspect(bind)
    columns = {row["name"]: row for row in inspector.get_columns("pending_external_auth")}
    required = {
        "token_hash", "provider", "provider_subject", "proof_hash", "display_name",
        "created_at", "expires_at", "consumed_at",
    }
    unique_sets = {
        tuple(row.get("column_names") or ())
        for row in inspector.get_unique_constraints("pending_external_auth")
    }
    checks = {row.get("name") for row in inspector.get_check_constraints("pending_external_auth")}
    indexes = {row.get("name") for row in inspector.get_indexes("pending_external_auth")}
    if (
        set(columns) != required
        or inspector.get_pk_constraint("pending_external_auth").get("constrained_columns")
        != ["token_hash"]
        or any(columns[name]["nullable"] for name in required - {"consumed_at"})
        or ("provider", "proof_hash") not in unique_sets
        or "ck_pending_external_provider" not in checks
        or "ix_pending_external_auth_expires_at" not in indexes
    ):
        raise RuntimeError("Existing pending auth table requires schema review")


def downgrade() -> None:
    raise RuntimeError("manual migration required before removing pending auth evidence")
