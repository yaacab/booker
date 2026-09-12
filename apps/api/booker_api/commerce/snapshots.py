"""Database guard: published monetary terms cannot be edited, acknowledgements can."""

from sqlalchemy import text

IMMUTABLE_FIELDS = (
    "offer_id",
    "honorarium_rub",
    "commission_rate",
    "commission_rub",
    "total_rub",
    "currency",
    "terms",
    "customer_service_fee_rate",
    "customer_service_fee_rub",
    "supplier_service_fee_rate",
    "supplier_service_fee_rub",
    "customer_total_rub",
    "supplier_payout_rub",
    "platform_revenue_rub",
    "commercial_policy_version",
)
SQLITE_GUARD = (
    "CREATE TRIGGER IF NOT EXISTS immutable_offer_price BEFORE UPDATE ON offer_versions "
    "WHEN "
    + " OR ".join(f"OLD.{field} IS NOT NEW.{field}" for field in IMMUTABLE_FIELDS)
    + " BEGIN SELECT RAISE(ABORT, 'OfferVersion terms are immutable'); END"
)


def install_sqlite_guard(bind) -> None:
    if bind.dialect.name == "sqlite":
        with bind.begin() as conn:
            conn.execute(text(SQLITE_GUARD))
