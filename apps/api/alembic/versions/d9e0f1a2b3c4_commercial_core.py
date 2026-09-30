"""Commercial catalog, billing and immutable fee snapshot columns.

Historic offer amounts are intentionally not backfilled.
"""

from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("monthly_price_rub", sa.Integer(), nullable=False),
        sa.Column("annual_price_rub", sa.Integer(), nullable=False),
        sa.Column("supplier_fee_bps", sa.Integer(), nullable=False),
        sa.Column("customer_fee_bps", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("features_json", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("customer_fee_bps >= 0 AND customer_fee_bps <= 10000"),
        sa.CheckConstraint("monthly_price_rub >= 0 AND annual_price_rub >= 0"),
        sa.CheckConstraint("supplier_fee_bps >= 0 AND supplier_fee_bps <= 10000"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "version", name="uq_commercial_plan_version"),
    )
    op.create_index(op.f("ix_commercial_plans_code"), "commercial_plans", ["code"], unique=False)
    op.create_table(
        "promotion_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("price_rub", sa.Integer(), nullable=False),
        sa.Column("duration_hours", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("price_rub >= 0 AND duration_hours > 0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audience", "code", "version", name="uq_promotion_product_version"),
    )
    op.create_table(
        "billing_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("product_kind", sa.String(length=32), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_reference", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('created','pending_payment','paid','failed','cancelled','refunded')"
        ),
        sa.CheckConstraint("amount_rub >= 0"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_billing_order_idempotency"
        ),
    )
    op.create_index(
        op.f("ix_billing_orders_organization_id"),
        "billing_orders",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("billing_period", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("next_plan_code", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=128), nullable=True),
        sa.Column("last_billing_order_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("billing_period IN ('monthly','annual','manual')"),
        sa.CheckConstraint(
            "status IN ('pending','trial','active','past_due','cancelled','expired')"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_table(
        "commerce_webhook_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["billing_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_commerce_webhook_event"),
    )
    op.create_table(
        "promotion_campaigns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("billing_order_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','pending_payment','scheduled','active','expired','cancelled','rejected')"
        ),
        sa.CheckConstraint("target_type IN ('artist','venue')"),
        sa.ForeignKeyConstraint(
            ["billing_order_id"],
            ["billing_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("billing_order_id"),
    )
    op.create_index(
        op.f("ix_promotion_campaigns_organization_id"),
        "promotion_campaigns",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_promotion_campaigns_status"), "promotion_campaigns", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_promotion_campaigns_target_id"), "promotion_campaigns", ["target_id"], unique=False
    )
    op.add_column(
        "offer_versions", sa.Column("customer_service_fee_rate", sa.Float(), nullable=True)
    )
    op.add_column(
        "offer_versions", sa.Column("customer_service_fee_rub", sa.Integer(), nullable=True)
    )
    op.add_column(
        "offer_versions", sa.Column("supplier_service_fee_rate", sa.Float(), nullable=True)
    )
    op.add_column(
        "offer_versions", sa.Column("supplier_service_fee_rub", sa.Integer(), nullable=True)
    )
    op.add_column("offer_versions", sa.Column("customer_total_rub", sa.Integer(), nullable=True))
    op.add_column("offer_versions", sa.Column("supplier_payout_rub", sa.Integer(), nullable=True))
    op.add_column("offer_versions", sa.Column("platform_revenue_rub", sa.Integer(), nullable=True))
    op.add_column(
        "offer_versions",
        sa.Column("commercial_policy_version", sa.String(length=128), nullable=True),
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER IF NOT EXISTS immutable_offer_price BEFORE UPDATE ON offer_versions WHEN OLD.offer_id IS NOT NEW.offer_id OR OLD.honorarium_rub IS NOT NEW.honorarium_rub OR OLD.commission_rate IS NOT NEW.commission_rate OR OLD.commission_rub IS NOT NEW.commission_rub OR OLD.total_rub IS NOT NEW.total_rub OR OLD.currency IS NOT NEW.currency OR OLD.terms IS NOT NEW.terms OR OLD.customer_service_fee_rate IS NOT NEW.customer_service_fee_rate OR OLD.customer_service_fee_rub IS NOT NEW.customer_service_fee_rub OR OLD.supplier_service_fee_rate IS NOT NEW.supplier_service_fee_rate OR OLD.supplier_service_fee_rub IS NOT NEW.supplier_service_fee_rub OR OLD.customer_total_rub IS NOT NEW.customer_total_rub OR OLD.supplier_payout_rub IS NOT NEW.supplier_payout_rub OR OLD.platform_revenue_rub IS NOT NEW.platform_revenue_rub OR OLD.commercial_policy_version IS NOT NEW.commercial_policy_version BEGIN SELECT RAISE(ABORT, 'OfferVersion terms are immutable'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_offer_price_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.offer_id IS DISTINCT FROM NEW.offer_id OR OLD.honorarium_rub IS DISTINCT FROM NEW.honorarium_rub OR OLD.commission_rate IS DISTINCT FROM NEW.commission_rate OR OLD.commission_rub IS DISTINCT FROM NEW.commission_rub OR OLD.total_rub IS DISTINCT FROM NEW.total_rub OR OLD.currency IS DISTINCT FROM NEW.currency OR OLD.terms IS DISTINCT FROM NEW.terms OR OLD.customer_service_fee_rate IS DISTINCT FROM NEW.customer_service_fee_rate OR OLD.customer_service_fee_rub IS DISTINCT FROM NEW.customer_service_fee_rub OR OLD.supplier_service_fee_rate IS DISTINCT FROM NEW.supplier_service_fee_rate OR OLD.supplier_service_fee_rub IS DISTINCT FROM NEW.supplier_service_fee_rub OR OLD.customer_total_rub IS DISTINCT FROM NEW.customer_total_rub OR OLD.supplier_payout_rub IS DISTINCT FROM NEW.supplier_payout_rub OR OLD.platform_revenue_rub IS DISTINCT FROM NEW.platform_revenue_rub OR OLD.commercial_policy_version IS DISTINCT FROM NEW.commercial_policy_version THEN RAISE EXCEPTION 'OfferVersion terms are immutable'; END IF; RETURN NEW; END; $$")
        op.execute("CREATE TRIGGER immutable_offer_price BEFORE UPDATE ON offer_versions "
                   "FOR EACH ROW EXECUTE FUNCTION reject_offer_price_change()")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS immutable_offer_price")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS immutable_offer_price ON offer_versions")
        op.execute("DROP FUNCTION IF EXISTS reject_offer_price_change()")
    op.drop_column("offer_versions", "commercial_policy_version")
    op.drop_column("offer_versions", "platform_revenue_rub")
    op.drop_column("offer_versions", "supplier_payout_rub")
    op.drop_column("offer_versions", "customer_total_rub")
    op.drop_column("offer_versions", "supplier_service_fee_rub")
    op.drop_column("offer_versions", "supplier_service_fee_rate")
    op.drop_column("offer_versions", "customer_service_fee_rub")
    op.drop_column("offer_versions", "customer_service_fee_rate")
    op.drop_index(op.f("ix_promotion_campaigns_target_id"), table_name="promotion_campaigns")
    op.drop_index(op.f("ix_promotion_campaigns_status"), table_name="promotion_campaigns")
    op.drop_index(op.f("ix_promotion_campaigns_organization_id"), table_name="promotion_campaigns")
    op.drop_table("promotion_campaigns")
    op.drop_table("commerce_webhook_events")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_billing_orders_organization_id"), table_name="billing_orders")
    op.drop_table("billing_orders")
    op.drop_table("promotion_products")
    op.drop_index(op.f("ix_commercial_plans_code"), table_name="commercial_plans")
    op.drop_table("commercial_plans")
