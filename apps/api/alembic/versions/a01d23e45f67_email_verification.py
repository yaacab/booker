"""Track new-account email proof without inventing proof for legacy accounts.

Revision ID: a01d23e45f67
Revises: ffbc123cd4e6
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a01d23e45f67"
down_revision: str | None = "ffbc123cd4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "email_verification_required_at" not in columns:
        op.add_column("users", sa.Column("email_verification_required_at", sa.DateTime(timezone=True)))
    if "email_verified_at" not in columns:
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    if "email_verification_challenges" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "email_verification_challenges",
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("target_email", sa.String(255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_email_verification_challenges_user_id",
            "email_verification_challenges", ["user_id"],
        )
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS users_admin_verified_email")
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS users_admin_verified_email "
            "BEFORE UPDATE OF is_platform_admin, email_verified_at, "
            "email_verification_required_at ON users "
            "WHEN NEW.is_platform_admin = 1 AND NEW.email_verified_at IS NULL "
            "AND (OLD.is_platform_admin = 0 OR NEW.email_verification_required_at IS NOT NULL) "
            "BEGIN SELECT RAISE(ABORT, 'admin email verification required'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS users_admin_verified_email_insert "
            "BEFORE INSERT ON users "
            "WHEN NEW.is_platform_admin = 1 AND NEW.email_verified_at IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'admin email verification required'); END"
        )
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS users_admin_verified_email ON users")
        op.execute("DROP TRIGGER IF EXISTS users_admin_verified_email_insert ON users")
        op.execute("""
            CREATE OR REPLACE FUNCTION booker_admin_verified_email_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'INSERT' THEN
                IF NEW.is_platform_admin AND NEW.email_verified_at IS NULL THEN
                  RAISE EXCEPTION 'admin email verification required';
                END IF;
              ELSIF NEW.is_platform_admin AND NEW.email_verified_at IS NULL
                    AND (NOT OLD.is_platform_admin OR NEW.email_verification_required_at IS NOT NULL) THEN
                RAISE EXCEPTION 'admin email verification required';
              END IF;
              RETURN NEW;
            END $$
        """)
        op.execute("""
            CREATE TRIGGER users_admin_verified_email
            BEFORE UPDATE OF is_platform_admin, email_verified_at,
            email_verification_required_at ON users
            FOR EACH ROW EXECUTE FUNCTION booker_admin_verified_email_guard()
        """)
        op.execute("""
            CREATE TRIGGER users_admin_verified_email_insert BEFORE INSERT ON users
            FOR EACH ROW EXECUTE FUNCTION booker_admin_verified_email_guard()
        """)


def downgrade() -> None:
    raise RuntimeError("manual migration required for email verification evidence")
