"""Bind technical draft acknowledgements to immutable text and per-actor challenges.

Revision ID: ffbc123cd4e6
Revises: feab012bc3d5
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ffbc123cd4e6"
down_revision: str | None = "feab012bc3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    contract_columns = {column["name"] for column in inspector.get_columns("contracts")}
    contract_indexes = {index["name"] for index in inspector.get_indexes("contracts")}
    if "uq_contract_booking" not in contract_indexes:
        op.create_index("uq_contract_booking", "contracts", ["booking_id"], unique=True)
    if "offer_version_id" not in contract_columns:
        op.add_column("contracts", sa.Column("offer_version_id", sa.String(36), nullable=True))
    if "body_sha256" not in contract_columns:
        op.add_column("contracts", sa.Column("body_sha256", sa.String(64), nullable=True))
    if "effect" not in contract_columns:
        op.add_column("contracts", sa.Column("effect", sa.String(48), nullable=False, server_default="legacy_unbound"))
    if "legal_pack_version" not in contract_columns:
        op.add_column("contracts", sa.Column("legal_pack_version", sa.String(48), nullable=False, server_default="legacy_unknown"))
    op.execute("UPDATE contracts SET otp_customer = NULL, otp_supplier = NULL")
    if bind.dialect.name != "sqlite":
        foreign_keys = {key.get("name") for key in inspector.get_foreign_keys("contracts")}
        if "fk_contract_offer_version" not in foreign_keys:
            op.create_foreign_key("fk_contract_offer_version", "contracts", "offer_versions", ["offer_version_id"], ["id"])
    signature_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("contract_signatures")
    }
    if "offer_version_id" not in signature_columns:
        op.add_column("contract_signatures", sa.Column("offer_version_id", sa.String(36), nullable=True))
    if "body_sha256" not in signature_columns:
        op.add_column("contract_signatures", sa.Column("body_sha256", sa.String(64), nullable=True))
    if "effect" not in signature_columns:
        op.add_column("contract_signatures", sa.Column("effect", sa.String(48), nullable=False, server_default="legacy_unbound"))
    if bind.dialect.name != "sqlite":
        signature_foreign_keys = {
            key.get("name") for key in sa.inspect(bind).get_foreign_keys("contract_signatures")
        }
        if "fk_signature_offer_version" not in signature_foreign_keys:
            op.create_foreign_key("fk_signature_offer_version", "contract_signatures", "offer_versions", ["offer_version_id"], ["id"])
    table_names = set(sa.inspect(bind).get_table_names())
    if "contract_challenges" not in table_names:
        op.create_table(
            "contract_challenges",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("contracts.id"), nullable=False),
            sa.Column("side", sa.String(16), nullable=False),
            sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("otp_hash", sa.String(160), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        )
    challenge_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("contract_challenges")
    }
    if "ix_contract_challenges_contract_id" not in challenge_indexes:
        op.create_index("ix_contract_challenges_contract_id", "contract_challenges", ["contract_id"])
    # Existing contracts/signatures remain legacy_unbound and are intentionally unusable for new acknowledgements.
    if bind.dialect.name == "sqlite":
        op.execute("""CREATE TRIGGER IF NOT EXISTS contracts_snapshot_immutable BEFORE UPDATE ON contracts
            WHEN NEW.body IS NOT OLD.body OR NEW.offer_version_id IS NOT OLD.offer_version_id
              OR NEW.body_sha256 IS NOT OLD.body_sha256 OR NEW.effect IS NOT OLD.effect
              OR NEW.template_key IS NOT OLD.template_key
              OR NEW.legal_pack_version IS NOT OLD.legal_pack_version
            BEGIN SELECT RAISE(ABORT, 'contract snapshot is immutable'); END""")
        op.execute("""CREATE TRIGGER IF NOT EXISTS contracts_no_delete BEFORE DELETE ON contracts
            BEGIN SELECT RAISE(ABORT, 'contract snapshot is immutable'); END""")
        op.execute("""CREATE TRIGGER IF NOT EXISTS contract_challenges_update_guard BEFORE UPDATE ON contract_challenges
            WHEN NEW.id IS NOT OLD.id OR NEW.contract_id IS NOT OLD.contract_id
              OR NEW.side IS NOT OLD.side OR NEW.actor_user_id IS NOT OLD.actor_user_id
              OR NEW.otp_hash IS NOT OLD.otp_hash OR NEW.expires_at IS NOT OLD.expires_at
              OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL
            BEGIN SELECT RAISE(ABORT, 'contract challenge is immutable'); END""")
        op.execute("""CREATE TRIGGER IF NOT EXISTS contract_challenges_no_delete BEFORE DELETE ON contract_challenges
            BEGIN SELECT RAISE(ABORT, 'contract challenge is immutable'); END""")
        for table in ("contracts", "contract_signatures"):
            op.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_offer_version_fk_insert
                BEFORE INSERT ON {table} WHEN NEW.offer_version_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM offer_versions WHERE id = NEW.offer_version_id)
                BEGIN SELECT RAISE(ABORT, 'offer version does not exist'); END""")
            op.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_offer_version_fk_update
                BEFORE UPDATE OF offer_version_id ON {table} WHEN NEW.offer_version_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM offer_versions WHERE id = NEW.offer_version_id)
                BEGIN SELECT RAISE(ABORT, 'offer version does not exist'); END""")
    elif bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION booker_contract_snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'contract snapshot is immutable'; END IF;
                IF NEW.body IS DISTINCT FROM OLD.body OR NEW.offer_version_id IS DISTINCT FROM OLD.offer_version_id
                   OR NEW.body_sha256 IS DISTINCT FROM OLD.body_sha256 OR NEW.effect IS DISTINCT FROM OLD.effect
                   OR NEW.template_key IS DISTINCT FROM OLD.template_key
                   OR NEW.legal_pack_version IS DISTINCT FROM OLD.legal_pack_version THEN
                    RAISE EXCEPTION 'contract snapshot is immutable';
                END IF;
                RETURN NEW;
            END $$""")
        op.execute("""CREATE TRIGGER contracts_snapshot_immutable BEFORE UPDATE OR DELETE ON contracts
            FOR EACH ROW EXECUTE FUNCTION booker_contract_snapshot_guard()""")
        op.execute("""CREATE FUNCTION booker_contract_challenge_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'contract challenge is immutable'; END IF;
                IF NEW.id IS DISTINCT FROM OLD.id OR NEW.contract_id IS DISTINCT FROM OLD.contract_id
                   OR NEW.side IS DISTINCT FROM OLD.side OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
                   OR NEW.otp_hash IS DISTINCT FROM OLD.otp_hash
                   OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
                   OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL THEN
                    RAISE EXCEPTION 'contract challenge is immutable';
                END IF;
                RETURN NEW;
            END $$""")
        op.execute("""CREATE TRIGGER contract_challenges_update_guard BEFORE UPDATE OR DELETE ON contract_challenges
            FOR EACH ROW EXECUTE FUNCTION booker_contract_challenge_guard()""")


def downgrade() -> None:
    raise RuntimeError("contract acknowledgement evidence is append-only; manual migration required")
