from datetime import timedelta
from itertools import pairwise

import pytest

from booker_api.models import AuditLog, AvailabilitySlot, PromotionCampaign, Subscription
from booker_api.security import now
from tests.conftest import contract_otps
from tests.test_commerce import complete, org_user
from tests.test_commerce import stub as _commerce_stub

stub = _commerce_stub


@pytest.fixture()
def supply(client):
    user, headers, org = org_user(client)
    start = (now() + timedelta(days=8)).replace(hour=18, minute=0, second=0, microsecond=0)
    profiles = []
    for i in range(10):
        artist = client.post(
            "/artists",
            headers=headers,
            json={
                "organization_id": org,
                "name": f"DJ {i}",
                "category": "dj",
                "city": "Москва",
                "rider": {"format": "corporate", "travel_ok": False},
            },
        )
        assert artist.status_code == 200, artist.text
        artist = artist.json()
        slot = client.post(
            "/slots",
            headers=headers,
            json={
                "resource_type": "artist",
                "resource_id": artist["id"],
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=4)).isoformat(),
            },
        )
        assert slot.status_code == 200, slot.text
        tariff = client.post(
            f"/artists/{artist['id']}/tariffs",
            headers=headers,
            json={"title": "Сет", "honorarium_rub": 10000 + i * 1000},
        )
        assert tariff.status_code == 200, tariff.text
        profiles.append(artist["id"])
    return {"user": user, "headers": headers, "org": org, "profiles": profiles, "start": start}


def promote(client, supply, index=0, *, credit=False, code="BOOST_24H", key=None):
    return client.post(
        f"/commerce/organizations/{supply['org']}/promotions",
        headers=supply["headers"],
        json={
            "target_type": "artist",
            "target_id": supply["profiles"][index],
            "product_code": code,
            "use_credit": credit,
            "idempotency_key": key or f"promotion-{index}",
        },
    )


def search(client, supply, **extra):
    params = {
        "date": supply["start"].isoformat(),
        "city": "Москва",
        "kind": "artist",
        "category": "dj",
        **extra,
    }
    response = client.get("/catalog/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_paid_insertion_cap_label_organic_order_and_idempotency(client, SessionLocal, supply, stub):
    organic = [item["id"] for item in search(client, supply)]
    for index in range(4):
        result = promote(client, supply, index)
        assert result.status_code == 200, result.text
        campaign = result.json()
        assert campaign["status"] == "pending_payment"
        complete(client, supply["headers"], campaign["order"])
        replay = promote(client, supply, index)
        assert replay.json()["id"] == campaign["id"]
    results = search(client, supply)
    paid = [i for i, item in enumerate(results) if item["sponsored"]]
    assert len(paid) == 2
    assert all(b - a > 1 for a, b in pairwise(paid))
    assert len({item["id"] for item in results}) == 10
    assert all(
        item["sponsored_label"] == "Продвижение" and item["promotion_touch_id"]
        for item in results
        if item["sponsored"]
    )
    assert [item["id"] for item in sorted(results, key=lambda i: i["organic_rank"])] == organic
    with SessionLocal() as db:
        assert db.query(PromotionCampaign).count() == 4
        assert db.query(AuditLog).filter_by(action="promotion.started").count() == 4


def test_wrong_city_category_budget_and_busy_date_never_sponsored(
    client, SessionLocal, supply, stub
):
    promoted = promote(client, supply, index=9).json()
    complete(client, supply["headers"], promoted["order"])
    assert any(item["sponsored"] for item in search(client, supply))
    assert search(client, supply, city="Казань") == []
    assert search(client, supply, category="photo") == []
    assert all(
        item["id"] != supply["profiles"][9] for item in search(client, supply, budget_max=15000)
    )
    with SessionLocal() as db:
        db.add(
            AvailabilitySlot(
                resource_type="artist",
                resource_id=supply["profiles"][9],
                starts_at=supply["start"],
                ends_at=supply["start"] + timedelta(hours=4),
                status="busy",
            )
        )
        db.commit()
    assert all(item["id"] != supply["profiles"][9] for item in search(client, supply))
    assert not any(item["sponsored"] for item in search(client, supply))


def test_no_paid_insertion_when_less_than_five_results(client, supply, stub):
    campaign = promote(client, supply).json()
    complete(client, supply["headers"], campaign["order"])
    results = search(client, supply, budget_max=13000)
    assert len(results) == 4 and all(not item["sponsored"] for item in results)


def test_foreign_profile_campaign_and_analytics_are_forbidden(client, supply):
    _, other_headers, other_org = org_user(client, suffix="outside")
    body = {
        "target_type": "artist",
        "target_id": supply["profiles"][0],
        "product_code": "BOOST_24H",
        "idempotency_key": "foreign",
    }
    assert (
        client.post(
            f"/commerce/organizations/{other_org}/promotions", headers=other_headers, json=body
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/commerce/organizations/{supply['org']}/promotions", headers=other_headers, json=body
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/commerce/organizations/{supply['org']}/promotions", headers=other_headers
        ).status_code
        == 403
    )
    campaign = promote(client, supply).json()
    assert (
        client.post(
            f"/commerce/promotions/{campaign['id']}/cancel", headers=other_headers
        ).status_code
        == 403
    )


def test_monthly_credits_entitlement_and_idempotency(client, SessionLocal, supply):
    assert promote(client, supply, credit=True).status_code == 409
    with SessionLocal() as db:
        db.add(
            Subscription(
                organization_id=supply["org"],
                plan_code="artist_pro",
                billing_period="manual",
                status="active",
                starts_at=now() - timedelta(days=1),
                current_period_end=now() + timedelta(days=30),
                provider="manual",
            )
        )
        db.commit()
    first = promote(client, supply, credit=True)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "active" and first.json()["order"] is None
    assert promote(client, supply, credit=True).json()["id"] == first.json()["id"]
    assert promote(client, supply, 1, credit=True).status_code == 200
    assert promote(client, supply, 2, credit=True).status_code == 409
    assert promote(client, supply, 3, credit=True, code="BOOST_7D").status_code == 422
    stats = client.get(
        f"/commerce/organizations/{supply['org']}/promotions", headers=supply["headers"]
    ).json()
    assert stats["credits"]["remaining"] == 0 and stats["credits"]["used"] == 2
    assert promote(client, supply, 3, code="FEATURED_7D").status_code == 403


def test_expired_campaign_not_inserted_and_expiry_audited_once(client, SessionLocal, supply, stub):
    campaign = promote(client, supply).json()
    complete(client, supply["headers"], campaign["order"])
    with SessionLocal() as db:
        db.get(PromotionCampaign, campaign["id"]).ends_at = now() - timedelta(seconds=1)
        db.commit()
    for _ in range(2):
        assert not any(item["sponsored"] for item in search(client, supply))
    with SessionLocal() as db:
        assert db.get(PromotionCampaign, campaign["id"]).status == "expired"
        assert (
            db.query(AuditLog)
            .filter_by(action="promotion.expired", entity_id=campaign["id"])
            .count()
            == 1
        )


def test_real_request_attribution_uses_issued_clicked_matching_touch(
    client, SessionLocal, supply, stub
):
    campaign = promote(client, supply).json()
    complete(client, supply["headers"], campaign["order"])
    item = next(item for item in search(client, supply) if item["sponsored"])
    touch = item["promotion_touch_id"]
    _, headers, org = org_user(client, kind="customer", suffix="customer")
    for _ in range(2):
        response = client.post(f"/commerce/promotion-touches/{touch}", json={"action": "click"})
        assert response.status_code == 200, response.text
    event = client.post(
        "/events",
        headers=headers,
        json={
            "organization_id": org,
            "title": "Событие",
            "event_date": supply["start"].isoformat(),
        },
    ).json()
    # Token cannot attribute a request for a different artist.
    wrong = client.post(
        f"/events/{event['id']}/requests",
        headers=headers,
        json={
            "resource_type": "artist",
            "resource_id": supply["profiles"][1],
            "promotion_touch_id": touch,
        },
    )
    assert wrong.status_code == 200
    good = client.post(
        f"/events/{event['id']}/requests",
        headers=headers,
        json={"resource_type": "artist", "resource_id": item["id"], "promotion_touch_id": touch},
    )
    assert good.status_code == 200, good.text
    # Confirm through the public deal flow; a request alone is never a booking.
    with SessionLocal() as db:
        slot_id = (
            db.query(AvailabilitySlot).filter_by(resource_id=item["id"], status="open").first().id
        )
    offer = client.post(
        f"/requests/{good.json()['id']}/offers",
        headers=supply["headers"],
        json={"honorarium_rub": 20000, "slot_id": slot_id, "terms": "Сет"},
    )
    assert offer.status_code == 200, offer.text
    offer = offer.json()
    for side, side_headers in (("supplier", supply["headers"]), ("customer", headers)):
        ack = client.post(f"/offers/{offer['id']}/ack", headers=side_headers, json={"side": side})
        assert ack.status_code == 200, ack.text
    booking_id = offer["booking_id"]
    held = client.post(f"/bookings/{booking_id}/hold", headers=headers)
    assert held.status_code == 200, held.text
    contract = client.post(f"/bookings/{booking_id}/contract", headers=headers).json()
    otps = contract_otps(SessionLocal, contract["id"])
    for side, side_headers in (("supplier", supply["headers"]), ("customer", headers)):
        signed = client.post(
            f"/contracts/{contract['id']}/sign",
            headers=side_headers,
            json={"side": side, "otp": otps[f"otp_{side}"]},
        )
        assert signed.status_code == 200, signed.text
    payment = client.post(
        f"/bookings/{booking_id}/payments",
        headers=headers,
        json={"idempotency_key": "attributed-payment"},
    ).json()
    for _ in range(2):
        paid = client.post(
            f"/payments/{payment['id']}/stub-complete",
            headers=headers,
            json={"status": "succeeded"},
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["booking_status"] == "Confirmed"
    summary = client.get(
        f"/commerce/organizations/{supply['org']}/promotions", headers=supply["headers"]
    ).json()["items"][0]
    assert summary["clicks"] == 1 and summary["requests"] == 1
    assert summary["bookings"] == 1
    assert summary["impressions"] == 1 and summary["ctr"] == 1
    with SessionLocal() as db:
        assert (
            db.query(AuditLog)
            .filter_by(action="promotion.request", entity_id=campaign["id"])
            .count()
            == 1
        )


def test_disabled_provider_does_not_start_paid_campaign(client, supply):
    result = promote(client, supply).json()
    assert result["status"] == "pending_payment"
    assert result["order"]["status"] == "created"
    assert not any(item["sponsored"] for item in search(client, supply))


def test_admin_prices_apply_only_to_new_promotion_orders(client, SessionLocal, supply, stub):
    from tests.test_commerce import platform_admin

    old = promote(client, supply).json()
    body = {"expected_version": 1, "price_rub": 590, "reason": "Изменение каталога"}
    route = "/admin/commerce/promotions/artist/BOOST_24H"
    assert client.put(route, headers=supply["headers"], json=body).status_code == 403
    admin = platform_admin(client, SessionLocal)
    changed = client.put(route, headers=admin, json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert client.put(route, headers=admin, json=body).status_code == 409
    newer = promote(client, supply, 1).json()
    assert newer["order"]["amount_rub"] == 590
    assert old["order"]["amount_rub"] == 490
    assert complete(client, supply["headers"], old["order"]).json()["status"] == "paid"
    assert promote(client, supply).json()["order"]["amount_rub"] == 490


def test_unclaimed_and_unpublished_venues_cannot_buy_placement(client, SessionLocal):
    from booker_api.models import Venue

    _, headers, org = org_user(client, kind="venue", suffix="promovenue")
    venue = client.post(
        "/venues",
        headers=headers,
        json={"organization_id": org, "name": "Зал", "city": "Москва", "capacity": 100},
    ).json()
    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        row.is_claimed = False
        row.availability_mode = "synthetic"
        db.commit()
    body = {
        "target_type": "venue",
        "target_id": venue["id"],
        "product_code": "BOOST_24H",
        "idempotency_key": "unclaimed",
    }
    route = f"/commerce/organizations/{org}/promotions"
    assert client.post(route, headers=headers, json=body).status_code == 422
    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        row.is_claimed = True
        row.availability_mode = "owner"
        row.moderation_status = "needs_review"
        db.commit()
    assert client.post(route, headers=headers, json=body).status_code == 422
