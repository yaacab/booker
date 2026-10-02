"""Add a verified, least-privilege support operator role.

Revision ID: a02e34f56a78
Revises: a01d23e45f67
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a02e34f56a78"
down_revision: str | None = "a01d23e45f67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "is_support_operator" not in columns:
        op.add_column(
            "users", sa.Column("is_support_operator", sa.Boolean(), nullable=False,
                               server_default=sa.false())
        )
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS users_support_operator_verified_email")
        op.execute(
            "CREATE TRIGGER users_support_operator_verified_email "
            "BEFORE UPDATE OF is_support_operator, email_verified_at ON users "
            "WHEN NEW.is_support_operator = 1 AND NEW.email_verified_at IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'support operator email verification required'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS users_support_operator_verified_email_insert "
            "BEFORE INSERT ON users "
            "WHEN NEW.is_support_operator = 1 AND NEW.email_verified_at IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'support operator email verification required'); END"
        )
    elif bind.dialect.name == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION booker_support_operator_verified_email_guard()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.is_support_operator AND NEW.email_verified_at IS NULL THEN
                RAISE EXCEPTION 'support operator email verification required';
              END IF;
              RETURN NEW;
            END $$
        """)
        op.execute("DROP TRIGGER IF EXISTS users_support_operator_verified_email ON users")
        op.execute("""
            CREATE TRIGGER users_support_operator_verified_email
            BEFORE INSERT OR UPDATE OF is_support_operator, email_verified_at ON users
            FOR EACH ROW EXECUTE FUNCTION booker_support_operator_verified_email_guard()
        """)


def downgrade() -> None:
    raise RuntimeError("manual migration required for support operator role evidence")
