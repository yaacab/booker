"""Commercial acceptance: actual API state, not just catalog values."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from booker_api.commerce.fees import calculate_fees
from booker_api.commerce.orders import period_end
from booker_api.commerce.provider import get_provider, signed_test_event
from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    BillingOrder,
    CommercialPlan,
    OfferVersion,
    Subscription,
    User,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_offers import ack_both, setup_negotiation


@pytest.fixture()
def stub(monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "commerce_provider", "stub")
    monkeypatch.setattr(settings, "commerce_allow_stub", True)
    monkeypatch.setattr(
        settings, "commerce_webhook_secret", "test-only-commerce-secret-32-characters"
    )


def org_user(client, kind="artist", suffix="one"):
    user = register(client, f"commerce-{suffix}@booker.test")
    headers = auth_header(user["token"])
    org = client.post("/orgs", headers=headers, json={"name": suffix, "kind": kind}).json()
    return user, headers, org["id"]


def platform_admin(client, SessionLocal):
    user = register(client, "commerce-admin@booker.test")
    with SessionLocal() as db:
        db.get(User, user["user_id"]).is_platform_admin = True
        db.commit()
    return auth_header(user["token"])


def buy(client, headers, org_id, code="artist_pro", key="first"):
    return client.post(
        f"/commerce/organizations/{org_id}/orders",
        headers=headers,
        json={
            "plan_code": code,
            "billing_period": "monthly",
            "idempotency_key": key,
        },
    )


def complete(client, headers, order):
    result = client.post(
        f"/commerce/orders/{order['id']}/test-complete", headers=headers, json={"status": "paid"}
    )
    assert result.status_code == 200, result.text
    return result


def state(client, headers, org_id):
    response = client.get(f"/commerce/organizations/{org_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_catalog_defaults_and_no_paid_trust(client):
    result = client.get("/commerce/catalog")
    assert result.status_code == 200
    data = result.json()
    plans = {p["code"]: p for p in data["plans"]}
    assert len(plans) == 8
    assert plans["artist_pro"]["monthly_price_rub"] == 1990
    assert plans["venue_premium"]["annual_price_rub"] == 79900
    assert plans["customer_business"]["annual_savings_rub"] == 9980
    assert len(data["promotions"]) == 8
    for p in plans.values():
        assert p["customer_fee_bps"] == 600
        assert not {"verified", "rating", "reviews"} & p["features"].keys()
        assert p["commercial_policy_version"]
    assert not data["checkout_available"]


@pytest.mark.parametrize(
    "supplier_bps,revenue,payout", [(400, 10000, 96000), (300, 9000, 97000), (200, 8000, 98000)]
)
def test_fee_breakdown(supplier_bps, revenue, payout):
    fees = calculate_fees(100000, 600, supplier_bps, "v3")
    assert fees["customer_total_rub"] == 106000
    assert fees["customer_service_fee_rub"] == 6000
    assert fees["supplier_payout_rub"] == payout
    assert fees["platform_revenue_rub"] == revenue
    assert fees["customer_total_rub"] - fees["supplier_payout_rub"] == revenue


@pytest.mark.parametrize(
    "amount,customer,supplier",
    [(1, 0, 0), (25, 2, 1), (50, 3, 2), (125, 8, 5), (99999, 6000, 4000)],
)
def test_rounding_half_up(amount, customer, supplier):
    fees = calculate_fees(amount, 600, 400, "rounding")
    assert fees["customer_service_fee_rub"] == customer
    assert fees["supplier_service_fee_rub"] == supplier
    assert isinstance(fees["customer_total_rub"], int)


@pytest.mark.parametrize("bad", [True, 1.5, 0, -1, "100"])
def test_non_integer_or_nonpositive_honorarium_rejected(bad):
    with pytest.raises(ValueError):
        calculate_fees(bad, 600, 400, "invalid")


def test_calendar_periods_not_fixed_thirty_days():
    assert period_end(datetime(2028, 1, 31, tzinfo=timezone.utc), "monthly").day == 29
    assert period_end(datetime(2028, 2, 29, tzinfo=timezone.utc), "annual") == datetime(
        2029, 2, 28, tzinfo=timezone.utc
    )


def test_disabled_order_no_fake_success_and_idempotency(client, SessionLocal):
    _, headers, org = org_user(client)
    first = buy(client, headers, org)
    assert first.status_code == 200, first.text
    order = first.json()
    assert order["status"] == "created" and order["paid_at"] is None
    assert order["checkout_url"] is None and not order["checkout_available"]
    replay = buy(client, headers, org)
    assert replay.json()["id"] == order["id"]
    assert buy(client, headers, org, "artist_premium").status_code == 409
    assert state(client, headers, org)["plan"]["code"] == "artist_free"
    assert (
        client.post(
            f"/commerce/orders/{order['id']}/test-complete",
            headers=headers,
            json={"status": "paid"},
        ).status_code
        == 404
    )
    with SessionLocal() as db:
        assert db.query(BillingOrder).count() == 1
        assert db.query(AuditLog).filter_by(action="subscription.checkout_started").count() == 1


def test_upgrade_entitlements_and_immutable_offer(client, SessionLocal, stub):
    ctx = setup_negotiation(client)
    headers = auth_header(ctx["owner"]["token"])
    org = ctx["artist_org"]["id"]
    original = ctx["offer"]["version"]
    assert original["supplier_service_fee_rub"] == 4000
    order = buy(client, headers, org).json()
    assert state(client, headers, org)["plan"]["code"] == "artist_free"
    complete(client, headers, order)
    assert state(client, headers, org)["features"]["analytics.advanced"] is True
    assert state(client, headers, org)["plan"]["code"] == "artist_pro"
    for _ in range(2):
        complete(client, headers, order)
    response = client.post(
        f"/offers/{ctx['offer']['id']}/versions", headers=headers, json={"honorarium_rub": 100000}
    )
    assert response.status_code == 200, response.text
    new = response.json()
    assert new["supplier_service_fee_rub"] == 3000
    assert new["commercial_policy_version"] != original["commercial_policy_version"]
    with SessionLocal() as db:
        old = db.get(OfferVersion, original["id"])
        assert old.supplier_service_fee_rub == 4000
        assert old.total_rub == 106000
        assert db.query(AuditLog).filter_by(action="subscription.activated").count() == 1
    premium = buy(client, headers, org, "artist_premium", "premium").json()
    complete(client, headers, premium)
    assert state(client, headers, org)["features"]["analytics.benchmark"] is True
    ack_both(client, ctx)


def test_database_rejects_price_mutation_but_allows_ack(client, SessionLocal):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE offer_versions SET total_rub = 1 WHERE id = :id"),
                {"id": ctx["offer"]["version"]["id"]},
            )
            db.commit()
        db.rollback()
        assert db.get(OfferVersion, ctx["offer"]["version"]["id"]).total_rub == 106000


def test_expiry_cancellation_and_scheduled_downgrade(client, SessionLocal, stub):
    _, headers, org = org_user(client)
    order = buy(client, headers, org, "artist_premium").json()
    complete(client, headers, order)
    change = client.post(
        f"/commerce/organizations/{org}/subscription/change",
        headers=headers,
        json={"plan_code": "artist_pro"},
    )
    assert change.status_code == 200, change.text
    current = state(client, headers, org)
    assert current["plan"]["code"] == "artist_premium"
    assert current["subscription"]["next_plan_code"] == "artist_pro"
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).one().current_period_end = (
            now() - timedelta(seconds=1)
        )
        db.commit()
    expired = state(client, headers, org)
    assert expired["plan"]["code"] == "artist_free"
    assert expired["subscription"]["status"] == "cancelled"
    # Scheduled paid plan requires a new successful period payment; no free activation.
    next_order = buy(client, headers, org, "artist_pro", "next-period").json()
    complete(client, headers, next_order)
    assert state(client, headers, org)["plan"]["code"] == "artist_pro"


def test_foreign_org_order_subscription_and_viewer_access(client, SessionLocal):
    _, headers, org = org_user(client)
    order = buy(client, headers, org).json()
    outsider, outsider_h, _ = org_user(client, suffix="outsider")
    assert client.get(f"/commerce/organizations/{org}", headers=outsider_h).status_code == 403
    assert client.get(f"/commerce/orders/{order['id']}", headers=outsider_h).status_code == 403
    assert buy(client, outsider_h, org).status_code == 403
    assert (
        client.post(
            f"/commerce/organizations/{org}/subscription/cancel", headers=outsider_h
        ).status_code
        == 403
    )
    client.post(
        f"/orgs/{org}/members",
        headers=headers,
        json={"user_id": outsider["user_id"], "role": "viewer"},
    )
    assert client.get(f"/commerce/organizations/{org}", headers=outsider_h).status_code == 200
    assert buy(client, outsider_h, org).status_code == 403
    assert buy(client, headers, org, "venue_pro", "foreign-audience").status_code == 422


def test_production_never_exposes_stub(client, monkeypatch, stub):
    monkeypatch.setattr(settings, "environment", "production")
    assert get_provider().name == "disabled"
    _, headers, org = org_user(client)
    order = buy(client, headers, org).json()
    assert order["provider"] == "disabled"
    assert (
        client.post(
            f"/commerce/orders/{order['id']}/test-complete",
            headers=headers,
            json={"status": "paid"},
        ).status_code
        == 404
    )


def test_webhook_signature_amount_replay_and_terminal_state(client, SessionLocal, stub):
    _, headers, org = org_user(client)
    order = buy(client, headers, org).json()
    payload, signature = signed_test_event(
        order["id"], f"stub:{order['id']}", order["amount_rub"], "paid", "evt-1"
    )
    assert (
        client.post(
            "/commerce/webhook", content=payload, headers={"X-Commerce-Signature": "bad"}
        ).status_code
        == 400
    )
    bad = json.loads(payload)
    bad["amount_rub"] += 1
    altered = json.dumps(bad).encode()
    signed = hmac.new(
        settings.commerce_webhook_secret.encode(), altered, hashlib.sha256
    ).hexdigest()
    assert (
        client.post(
            "/commerce/webhook", content=altered, headers={"X-Commerce-Signature": signed}
        ).status_code
        == 409
    )
    first = client.post(
        "/commerce/webhook", content=payload, headers={"X-Commerce-Signature": signature}
    )
    assert first.status_code == 200, first.text
    assert (
        client.post(
            "/commerce/webhook", content=payload, headers={"X-Commerce-Signature": signature}
        ).json()
        == first.json()
    )
    assert (
        client.post(
            "/commerce/webhook", content=altered, headers={"X-Commerce-Signature": signed}
        ).status_code
        == 409
    )
    failed, sig = signed_test_event(
        order["id"], f"stub:{order['id']}", order["amount_rub"], "failed", "evt-2"
    )
    assert (
        client.post(
            "/commerce/webhook", content=failed, headers={"X-Commerce-Signature": sig}
        ).status_code
        == 409
    )
    refund, sig = signed_test_event(
        order["id"], f"stub:{order['id']}", order["amount_rub"], "refunded", "evt-refund"
    )
    assert (
        client.post(
            "/commerce/webhook", content=refund, headers={"X-Commerce-Signature": sig}
        ).status_code
        == 200
    )
    assert state(client, headers, org)["plan"]["code"] == "artist_free"


def test_admin_only_versioned_prices_grants_and_revokes(client, SessionLocal):
    _, headers, org = org_user(client)
    admin = platform_admin(client, SessionLocal)
    plan = next(
        p for p in client.get("/commerce/catalog").json()["plans"] if p["code"] == "artist_pro"
    )
    update = {
        "expected_version": 1,
        "monthly_price_rub": 2500,
        "annual_price_rub": 25000,
        "supplier_fee_bps": 300,
        "customer_fee_bps": 600,
        "features": plan["features"],
        "reason": "New pricing",
    }
    assert (
        client.put("/admin/commerce/plans/artist_pro", headers=headers, json=update).status_code
        == 403
    )
    result = client.put("/admin/commerce/plans/artist_pro", headers=admin, json=update)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    assert (
        client.put("/admin/commerce/plans/artist_pro", headers=admin, json=update).status_code
        == 409
    )
    assert buy(client, headers, org).json()["amount_rub"] == 2500
    grant = {"plan_code": "artist_pro", "status": "trial", "days": 7, "reason": "Support trial"}
    assert (
        client.post(
            f"/admin/commerce/organizations/{org}/grant", headers=headers, json=grant
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/admin/commerce/organizations/{org}/grant", headers=admin, json=grant
        ).status_code
        == 200
    )
    assert state(client, headers, org)["plan"]["code"] == "artist_pro"
    grant["status"] = "past_due"
    client.post(f"/admin/commerce/organizations/{org}/grant", headers=admin, json=grant)
    assert state(client, headers, org)["plan"]["code"] == "artist_free"
    grant["status"] = "cancelled"
    client.post(f"/admin/commerce/organizations/{org}/grant", headers=admin, json=grant)
    with SessionLocal() as db:
        assert db.query(CommercialPlan).filter_by(code="artist_pro").count() == 2
        assert db.query(AuditLog).filter_by(action="commercial.plan_changed").count() == 1
        assert db.query(AuditLog).filter_by(action="subscription.admin_grant").count() == 3


def test_commercial_flag_does_not_remove_free_product_access(client, monkeypatch):
    monkeypatch.setattr(settings, "commercial_plans", False)
    assert client.get("/commerce/catalog").status_code == 404
    ctx = setup_negotiation(client)
    assert ctx["offer"]["version"]["quote_id"]
    assert ctx["offer"]["version"]["supplier_service_fee_rub"] == 4000
