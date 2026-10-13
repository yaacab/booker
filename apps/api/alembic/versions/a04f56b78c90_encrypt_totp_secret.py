"""Encrypt stored TOTP secrets without changing their application meaning.

Revision ID: a04f56b78c90
Revises: a03f45a67b89
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from booker_api.totp_storage import decrypt_totp_secret, encrypt_totp_secret

revision: str = "a04f56b78c90"
down_revision: str | None = "a03f45a67b89"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError("TOTP storage migration requires reviewed database engine")
    # Validate every row and the configured key before changing any stored data.
    rows = bind.execute(sa.text(
        "SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL"
    )).mappings().all()
    changes: list[tuple[str, str]] = []
    for row in rows:
        stored = row["totp_secret"]
        if stored.startswith("fernet:v1:"):
            decrypt_totp_secret(stored)  # Resume only if the configured key reads it.
            continue
        if len(stored) % 8 != 0 or not re.fullmatch(r"[A-Z2-7]{16,64}", stored):
            raise RuntimeError("Legacy TOTP data requires manual review before migration")
        changes.append((row["id"], encrypt_totp_secret(stored)))
    if bind.dialect.name == "postgresql":
        op.alter_column("users", "totp_secret", existing_type=sa.String(64), type_=sa.Text(),
                        existing_nullable=True)
    # SQLite VARCHAR length is advisory; avoid rebuilding users and losing its
    # existing email/role triggers. PostgreSQL must widen the physical column.
    for user_id, encrypted in changes:
        bind.execute(
            sa.text("UPDATE users SET totp_secret = :encrypted WHERE id = :user_id"),
            {"encrypted": encrypted, "user_id": user_id},
        )
    if bind.dialect.name == "sqlite":
        for action in ("INSERT", "UPDATE"):
            name = f"users_totp_ciphertext_{action.lower()}"
            target = "" if action == "INSERT" else "OF totp_secret "
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {action} {target}ON users "
                "WHEN NEW.totp_secret IS NOT NULL "
                "AND NEW.totp_secret NOT LIKE 'fernet:v1:%' "
                "BEGIN SELECT RAISE(ABORT, 'TOTP secret must be encrypted'); END"
            )
    else:
        op.create_check_constraint(
            "ck_users_totp_ciphertext", "users",
            "totp_secret IS NULL OR left(totp_secret, 10) = 'fernet:v1:'",
        )


def downgrade() -> None:
    raise RuntimeError("manual migration required before TOTP ciphertext data rollback")
