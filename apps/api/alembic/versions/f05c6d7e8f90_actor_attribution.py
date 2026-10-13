"""Add immutable offer acknowledgements and contract signatures.

Revision ID: f05c6d7e8f90
Revises: ef5b6c7d8e9f
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "f05c6d7e8f90"
down_revision: str | None = "ef5b6c7d8e9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_offer_acknowledgements() -> None:
    op.create_table(
        "offer_acknowledgements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("offer_version_id", sa.String(length=36), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_role_snapshot", sa.String(length=32), nullable=True),
        sa.Column("attribution_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("side IN ('customer', 'supplier')", name="ck_offer_ack_side"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["offer_version_id"], ["offer_versions.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_version_id", "actor_user_id"),
        sa.UniqueConstraint("offer_version_id", "side"),
    )
    op.create_index(
        "ix_offer_acknowledgements_offer_version_id",
        "offer_acknowledgements",
        ["offer_version_id"],
    )


def _create_contract_signatures() -> None:
    op.create_table(
        "contract_signatures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_role_snapshot", sa.String(length=32), nullable=True),
        sa.Column("auth_method", sa.String(length=16), nullable=False),
        sa.Column("attribution_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "side IN ('customer', 'supplier')", name="ck_contract_signature_side"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "actor_user_id"),
        sa.UniqueConstraint("contract_id", "side"),
    )
    op.create_index(
        "ix_contract_signatures_contract_id", "contract_signatures", ["contract_id"]
    )


def _install_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        for table in ("offer_acknowledgements", "contract_signatures"):
            for action in ("UPDATE", "DELETE"):
                bind.execute(
                    sa.text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} "
                        f"BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, "
                        f"'{table} is append-only'); END"
                    )
                )
    elif bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "CREATE OR REPLACE FUNCTION booker_reject_attestation_mutation() "
                "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
                "'deal attestations are append-only'; END; $$"
            )
        )
        for table in ("offer_acknowledgements", "contract_signatures"):
            bind.execute(
                sa.text(
                    f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION booker_reject_attestation_mutation()"
                )
            )


def upgrade() -> None:
    tables = _tables()
    if "offer_acknowledgements" not in tables:
        _create_offer_acknowledgements()
    if "contract_signatures" not in tables:
        _create_contract_signatures()

    bind = op.get_bind()
    legacy_acknowledgements = bind.execute(
        sa.text(
            "SELECT ov.id AS offer_version_id, sides.side, "
            "CASE sides.side WHEN 'customer' THEN c.customer_org_id "
            "ELSE c.supplier_org_id END AS organization_id, "
            "CURRENT_TIMESTAMP AS created_at "
            "FROM offer_versions ov JOIN offers o ON o.id = ov.offer_id "
            "JOIN conversations c ON c.request_id = o.request_id "
            "JOIN (SELECT 'customer' AS side UNION ALL SELECT 'supplier') sides ON 1=1 "
            "LEFT JOIN offer_acknowledgements oa ON oa.offer_version_id = ov.id "
            "AND oa.side = sides.side WHERE oa.id IS NULL AND "
            "((sides.side = 'customer' AND ov.customer_ack = 1) "
            "OR (sides.side = 'supplier' AND ov.supplier_ack = 1))"
        )
    ).mappings()
    for row in legacy_acknowledgements:
        bind.execute(
            sa.text(
                "INSERT INTO offer_acknowledgements "
                "(id, offer_version_id, side, organization_id, actor_user_id, "
                "actor_role_snapshot, attribution_status, created_at) VALUES "
                "(:id, :offer_version_id, :side, :organization_id, NULL, NULL, "
                "'legacy_unattributed', :created_at)"
            ),
            {"id": str(uuid4()), **dict(row)},
        )
    legacy_signatures = bind.execute(
        sa.text(
            "SELECT ct.id AS contract_id, sides.side, "
            "CASE sides.side WHEN 'customer' THEN cv.customer_org_id "
            "ELSE cv.supplier_org_id END AS organization_id, "
            "CURRENT_TIMESTAMP AS created_at "
            "FROM contracts ct JOIN bookings b ON b.id = ct.booking_id "
            "JOIN conversations cv ON cv.booking_id = b.id "
            "JOIN (SELECT 'customer' AS side UNION ALL SELECT 'supplier') sides ON 1=1 "
            "LEFT JOIN contract_signatures cs ON cs.contract_id = ct.id AND cs.side = sides.side "
            "WHERE cs.id IS NULL AND ((sides.side = 'customer' AND ct.customer_signed = 1) "
            "OR (sides.side = 'supplier' AND ct.supplier_signed = 1))"
        )
    ).mappings()
    for row in legacy_signatures:
        bind.execute(
            sa.text(
                "INSERT INTO contract_signatures "
                "(id, contract_id, side, organization_id, actor_user_id, actor_role_snapshot, "
                "auth_method, attribution_status, created_at) VALUES "
                "(:id, :contract_id, :side, :organization_id, NULL, NULL, 'legacy', "
                "'legacy_unattributed', :created_at)"
            ),
            {"id": str(uuid4()), **dict(row)},
        )
    _install_guards()


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM offer_acknowledgements) + "
            "(SELECT COUNT(*) FROM contract_signatures)"
        )
    ).scalar_one()
    if rows:
        raise RuntimeError("Refusing to discard immutable deal attestations")
    if bind.dialect.name == "postgresql":
        for table in ("offer_acknowledgements", "contract_signatures"):
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}"))
        bind.execute(sa.text("DROP FUNCTION IF EXISTS booker_reject_attestation_mutation()"))
    op.drop_index("ix_contract_signatures_contract_id", table_name="contract_signatures")
    op.drop_table("contract_signatures")
    op.drop_index(
        "ix_offer_acknowledgements_offer_version_id", table_name="offer_acknowledgements"
    )
    op.drop_table("offer_acknowledgements")
