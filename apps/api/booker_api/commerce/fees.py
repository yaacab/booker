"""Integer RUB calculation. Display rates never participate in arithmetic."""

from sqlalchemy.orm import Session

from booker_api.commerce.catalog import policy_version
from booker_api.commerce.entitlements import resolve_plan
from booker_api.models import OfferVersion

SNAPSHOT_FIELDS = (
    "customer_service_fee_rate",
    "customer_service_fee_rub",
    "supplier_service_fee_rate",
    "supplier_service_fee_rub",
    "customer_total_rub",
    "supplier_payout_rub",
    "platform_revenue_rub",
    "commercial_policy_version",
)


def round_fee(honorarium: int, basis_points: int) -> int:
    if type(honorarium) is not int or honorarium <= 0:
        raise ValueError("Гонорар должен быть положительным целым числом рублей")
    if type(basis_points) is not int or not 0 <= basis_points <= 10000:
        raise ValueError("Недопустимая ставка комиссии")
    return (honorarium * basis_points + 5000) // 10000


def calculate_fees(honorarium: int, customer_bps: int, supplier_bps: int, version: str) -> dict:
    customer_fee = round_fee(honorarium, customer_bps)
    supplier_fee = round_fee(honorarium, supplier_bps)
    return {
        "honorarium_rub": honorarium,
        "customer_service_fee_rate": customer_bps / 10000,
        "customer_service_fee_rub": customer_fee,
        "supplier_service_fee_rate": supplier_bps / 10000,
        "supplier_service_fee_rub": supplier_fee,
        "customer_total_rub": honorarium + customer_fee,
        "supplier_payout_rub": honorarium - supplier_fee,
        "platform_revenue_rub": customer_fee + supplier_fee,
        "commercial_policy_version": version,
        "currency": "RUB",
        # Backwards-compatible customer-side aliases; never platform revenue.
        "commission_rate": customer_bps / 10000,
        "commission_rub": customer_fee,
        "total_rub": honorarium + customer_fee,
    }


def offer_fees(db: Session, honorarium: int, supplier_org_id: str, customer_org_id: str) -> dict:
    supply = resolve_plan(db, supplier_org_id)
    customer = resolve_plan(db, customer_org_id)
    return calculate_fees(
        honorarium,
        customer.customer_fee_bps,
        supply.supplier_fee_bps,
        policy_version(supply, customer),
    )


def snapshot_payload(version: OfferVersion) -> dict:
    return {field: getattr(version, field) for field in SNAPSHOT_FIELDS}
