"""Snapshot payment deadlines and check-in policy.

Revision ID: f38f901ab2c3
Revises: f27e8f901ab2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f38f901ab2c3"
down_revision: str | None = "f27e8f901ab2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    offer_columns = {row["name"] for row in sa.inspect(bind).get_columns("offer_versions")}
    if "payment_terms_json" not in offer_columns:
        op.add_column(
            "offer_versions",
            sa.Column("payment_terms_json", sa.Text(), nullable=False, server_default="{}"),
        )
    obligation_columns = {
        row["name"] for row in sa.inspect(bind).get_columns("payment_obligations")
    }
    if "grace_until" not in obligation_columns:
        op.add_column(
            "payment_obligations",
            sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
        )
    if "required_before_check_in" not in obligation_columns:
        op.add_column(
            "payment_obligations",
            sa.Column(
                "required_before_check_in",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    bind.execute(
        sa.text(
            "UPDATE offer_versions SET payment_terms_json = :legacy "
            "WHERE payment_terms_json IS NULL OR payment_terms_json = :empty"
        ),
        {"legacy": '{"legacy_review_required":true}', "empty": "{}"},
    )
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS offer_versions_payment_terms_immutable "
            "BEFORE UPDATE OF payment_terms_json ON offer_versions "
            "BEGIN SELECT RAISE(ABORT, 'offer payment terms are immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS payment_obligations_deadlines_immutable "
            "BEFORE UPDATE OF due_at, grace_until, required_before_check_in "
            "ON payment_obligations "
            "BEGIN SELECT RAISE(ABORT, 'payment deadlines are immutable'); END"
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_offer_payment_terms_mutation() RETURNS trigger AS $$
            BEGIN
              IF NEW.payment_terms_json IS DISTINCT FROM OLD.payment_terms_json THEN
                RAISE EXCEPTION 'offer payment terms are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER offer_versions_payment_terms_immutable BEFORE UPDATE ON offer_versions "
            "FOR EACH ROW EXECUTE FUNCTION reject_offer_payment_terms_mutation()"
        )
        op.execute(
            """
            CREATE FUNCTION reject_payment_deadline_mutation() RETURNS trigger AS $$
            BEGIN
              IF NEW.due_at IS DISTINCT FROM OLD.due_at
                 OR NEW.grace_until IS DISTINCT FROM OLD.grace_until
                 OR NEW.required_before_check_in IS DISTINCT FROM OLD.required_before_check_in THEN
                RAISE EXCEPTION 'payment deadlines are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER payment_obligations_deadlines_immutable "
            "BEFORE UPDATE ON payment_obligations FOR EACH ROW "
            "EXECUTE FUNCTION reject_payment_deadline_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS offer_versions_payment_terms_immutable")
        op.execute("DROP TRIGGER IF EXISTS payment_obligations_deadlines_immutable")
    elif bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS offer_versions_payment_terms_immutable ON offer_versions"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS payment_obligations_deadlines_immutable "
            "ON payment_obligations"
        )
        op.execute("DROP FUNCTION IF EXISTS reject_offer_payment_terms_mutation()")
        op.execute("DROP FUNCTION IF EXISTS reject_payment_deadline_mutation()")
    op.drop_column("payment_obligations", "required_before_check_in")
    op.drop_column("payment_obligations", "grace_until")
    op.drop_column("offer_versions", "payment_terms_json")
