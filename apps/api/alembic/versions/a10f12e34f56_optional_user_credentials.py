"""Allow external-only users without inventing an email or local password.

Revision ID: a10f12e34f56
Revises: a09f01e23f45
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a10f12e34f56"
down_revision: str | None = "a09f01e23f45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError("Optional credentials require reviewed database engine")
    columns = {row["name"]: row for row in sa.inspect(bind).get_columns("users")}
    needs_email = not columns["email"]["nullable"]
    needs_password = not columns["password_hash"]["nullable"]
    if not (needs_email or needs_password):
        return

    if bind.dialect.name == "postgresql":
        if needs_email:
            op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
        if needs_password:
            op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
        op.create_check_constraint(
            "ck_users_email_proof_has_address", "users",
            "email IS NOT NULL OR email_verified_at IS NULL",
        )
        return

    # SQLite rebuilds the referenced table. Alembic copies data and indexes,
    # but SQLite drops table triggers. Preserve the exact reviewed trigger SQL.
    triggers = bind.execute(sa.text(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
        "AND tbl_name='users' AND sql IS NOT NULL ORDER BY name"
    )).all()
    # Older local databases can already contain unrelated FK violations.
    # This migration must introduce none; the release rehearsal independently
    # requires a clean source before any real database switch.
    existing_fk_violations = set(bind.execute(sa.text("PRAGMA foreign_key_check")).all())
    with op.batch_alter_table("users", recreate="always") as batch:
        if needs_email:
            batch.alter_column("email", existing_type=sa.String(255), nullable=True)
        if needs_password:
            batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
        batch.create_check_constraint(
            "ck_users_email_proof_has_address",
            "email IS NOT NULL OR email_verified_at IS NULL",
        )
    for _, sql in triggers:
        bind.execute(sa.text(sql))
    current = {row["name"]: row for row in sa.inspect(bind).get_columns("users")}
    if not current["email"]["nullable"] or not current["password_hash"]["nullable"]:
        raise RuntimeError("Optional credential migration did not update both columns")
    if set(bind.execute(sa.text("PRAGMA foreign_key_check")).all()) != existing_fk_violations:
        raise RuntimeError("Optional credential migration changed SQLite foreign-key violations")


def downgrade() -> None:
    raise RuntimeError("manual migration required after external-only accounts may exist")
