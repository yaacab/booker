from datetime import timedelta
from uuid import uuid4

import pytest

from booker_api.calendar import MSK
from booker_api.config import settings
from booker_api.models import (
    Artist,
    AuditLog,
    AvailabilitySlot,
    DiscoverySignal,
    Organization,
    Request,
    Subscription,
    Venue,
    VenuePhoto,
    VenueTariff,
)
from booker_api.security import now
from tests.conftest import activate_venue, auth_header, register
from tests.test_commerce import org_user
from tests.test_payments import _awaiting_payment


def create_profile(client, headers, org, name="Моя сцена"):
    result = client.post(
        "/artists",
        headers=headers,
        json={"organization_id": org, "name": name, "city": "Москва", "category": "dj"},
    )
    assert result.status_code == 200, result.text
    return result.json()["id"]


def grant(SessionLocal, org, code):
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(organization_id=org).first()
        if not sub:
            sub = Subscription(organization_id=org)
            db.add(sub)
        sub.plan_code = code
        sub.status = "active"
        sub.starts_at = now() - timedelta(days=1)
        sub.current_period_end = now() + timedelta(days=30)
        sub.billing_period = "manual"
        sub.provider = "manual"
        db.commit()


def test_free_growth_periods_authorization_and_expired_plan(client, SessionLocal, monkeypatch):
    _, headers, org = org_user(client)
    response = client.get(f"/organizations/{org}/growth", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available_periods"] == [7, 30]
    assert not data["profiles"] and data["funnel"]["requests"] == 0
    assert "losses" not in data
    assert data["response"]["median_seconds"] is None
    _, other_headers, _ = org_user(client, suffix="other")
    assert client.get(f"/organizations/{org}/growth", headers=other_headers).status_code == 403
    assert client.get(f"/organizations/{org}/growth?days=90", headers=headers).status_code == 403
    assert (
        client.get(f"/organizations/{org}/growth?target_id={uuid4()}", headers=headers).status_code
        == 403
    )
    assert client.get(f"/organizations/{org}/growth/export", headers=headers).status_code == 403
    grant(SessionLocal, org, "artist_premium")
    assert client.get(f"/organizations/{org}/growth?days=365", headers=headers).status_code == 200
    export = client.get(f"/organizations/{org}/growth/export", headers=headers)
    assert export.status_code == 200 and "metric,value,days" in export.text
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).first().current_period_end = (
            now() - timedelta(seconds=1)
        )
        db.commit()
    assert client.get(f"/organizations/{org}/growth?days=365", headers=headers).status_code == 403
    monkeypatch.setattr(settings, "artist_growth", False)
    assert client.get(f"/organizations/{org}/growth", headers=headers).status_code == 404


def test_discovery_is_deduplicated_excludes_owner_and_favorite_is_server_only(client):
    _, headers, org = org_user(client)
    artist = create_profile(client, headers, org)
    visitor = str(uuid4())
    body = {
        "target_type": "artist",
        "target_id": artist,
        "kind": "profile_view",
        "visitor_id": visitor,
    }
    assert client.post("/discovery/signals", json=body, headers=headers).status_code == 200
    assert (
        client.get(f"/organizations/{org}/growth", headers=headers).json()["funnel"][
            "profile_views"
        ]
        == 0
    )
    for _ in range(3):
        assert client.post("/discovery/signals", json=body).status_code == 200
        assert (
            client.post("/discovery/signals", json={**body, "kind": "impression"}).status_code
            == 200
        )
    assert client.post("/discovery/signals", json={**body, "kind": "favorite"}).status_code == 422
    _, customer_headers, customer_org = org_user(client, kind="customer", suffix="customer")
    for _ in range(2):
        assert (
            client.post(
                "/favorites",
                headers=customer_headers,
                json={
                    "target_type": "artist",
                    "target_id": artist,
                    "organization_id": customer_org,
                },
            ).status_code
            == 201
        )
    data = client.get(f"/organizations/{org}/growth", headers=headers).json()["funnel"]
    assert data["profile_views"] == data["impressions"] == data["favorites"] == 1
    assert (
        client.post("/discovery/signals", json={**body, "target_id": str(uuid4())}).status_code
        == 404
    )


@pytest.mark.parametrize("revocation", ["media", "calendar", "price", "partnership"])
def test_hidden_venue_signal_matches_missing_and_does_not_record(
    client, SessionLocal, revocation
):
    owner = register(client, f"growth-venue-{revocation}@booker.test")
    headers = auth_header(owner["token"])
    org_response = client.post(
        "/orgs", headers=headers, json={"name": "Площадка", "kind": "venue"}
    )
    assert org_response.status_code == 200, org_response.text
    org_id = org_response.json()["id"]
    venue_response = client.post(
        "/venues", headers=headers,
        json={"organization_id": org_id, "name": "Приватный зал", "capacity": 100},
    )
    assert venue_response.status_code == 200, venue_response.text
    venue_id = venue_response.json()["id"]
    activate_venue(client, venue_id)
    body = {
        "target_type": "venue", "target_id": venue_id,
        "kind": "profile_view", "visitor_id": str(uuid4()),
    }
    active = client.post("/discovery/signals", json=body)
    assert active.status_code == 200, active.text
    # A profile owner can still read their own historical analytics.
    own_growth = client.get(f"/organizations/{org_id}/growth", headers=headers)
    assert own_growth.status_code == 200, own_growth.text
    assert own_growth.json()["funnel"]["profile_views"] == 1

    with SessionLocal() as db:
        profile = db.get(Venue, venue_id)
        assert profile.moderation_status == "published"
        if revocation == "media":
            db.query(VenuePhoto).filter_by(venue_id=venue_id).delete()
        elif revocation == "calendar":
            db.query(AvailabilitySlot).filter_by(resource_type="hall").delete()
        elif revocation == "price":
            db.query(VenueTariff).filter_by(venue_id=venue_id).delete()
        else:
            profile.partnership_status = "claimed"
        db.commit()

    hidden = client.post("/discovery/signals", json={**body, "visitor_id": str(uuid4())})
    missing = client.post(
        "/discovery/signals",
        json={**body, "target_id": str(uuid4()), "visitor_id": str(uuid4())},
    )
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert client.post("/discovery/signals", headers=headers, json=body).status_code == 404
    with SessionLocal() as db:
        assert db.query(DiscoverySignal).filter_by(target_id=venue_id).count() == 1
        assert db.query(AuditLog).filter_by(action="discovery.profile_view").count() == 1
    own_growth = client.get(f"/organizations/{org_id}/growth", headers=headers)
    assert own_growth.status_code == 200
    assert own_growth.json()["funnel"]["profile_views"] == 1


def test_funnel_follows_actual_deal_and_public_response_is_measured(client):
    ctx = _awaiting_payment(client)
    org = ctx["artist_org"]["id"]
    headers = auth_header(ctx["owner"]["token"])
    before = client.get(f"/organizations/{org}/growth", headers=headers).json()
    assert (
        before["funnel"]["requests"] == before["funnel"]["offers"] == before["funnel"]["holds"] == 1
    )
    assert before["funnel"]["confirmed"] == before["confirmed_honorarium_rub"] == 0
    assert before["response"]["sample_size"] == 1
    facts = client.get(f"/artists/{ctx['artist']['id']}").json()["facts"]
    assert facts["response_metrics"]["sample_size"] == 1
    assert "пилоте" not in facts["response"] and facts["deals"] == 0
    paid = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        headers=auth_header(ctx["customer"]["token"]),
        json={"status": "succeeded"},
    )
    assert paid.status_code == 200
    after = client.get(f"/organizations/{org}/growth", headers=headers).json()
    assert after["funnel"]["confirmed"] == 1
    assert after["confirmed_honorarium_rub"] == 100000
    assert after["conversions"]["request_to_confirmed"] == 1


def test_loss_price_requires_explicit_customer_signal_and_cannot_be_overwritten(
    client, SessionLocal
):
    ctx = _awaiting_payment(client)
    org = ctx["artist_org"]["id"]
    supply_headers = auth_header(ctx["owner"]["token"])
    customer_headers = auth_header(ctx["customer"]["token"])
    grant(SessionLocal, org, "artist_pro")
    req_id = client.get("/requests", headers=supply_headers).json()["items"][0]["id"]
    route = f"/requests/{req_id}/loss-reason"
    assert client.post(route, headers=customer_headers, json={"reason": "price"}).status_code == 409
    with SessionLocal() as db:
        db.get(Request, req_id).status = "Cancelled"
        db.commit()
    before = client.get(f"/organizations/{org}/growth", headers=supply_headers).json()
    assert next(r for r in before["losses"] if r["reason"] == "unknown")["count"] == 1
    assert client.post(route, headers=supply_headers, json={"reason": "price"}).status_code == 422
    _, outsider, _ = org_user(client, suffix="outsider")
    assert client.post(route, headers=outsider, json={"reason": "price"}).status_code == 403
    for _ in range(2):
        assert (
            client.post(route, headers=customer_headers, json={"reason": "price"}).status_code
            == 200
        )
    assert client.post(route, headers=supply_headers, json={"reason": "unknown"}).status_code == 409
    after = client.get(f"/organizations/{org}/growth", headers=supply_headers).json()
    assert next(r for r in after["losses"] if r["reason"] == "price")["count"] == 1
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="request.loss_reason").count() == 1


def test_benchmark_requires_ten_independent_profiles_and_never_discloses_names(
    client, SessionLocal
):
    _, headers, org = org_user(client)
    artist = create_profile(client, headers, org)
    grant(SessionLocal, org, "artist_premium")
    route = f"/organizations/{org}/growth?target_id={artist}"
    peer_ids = []
    for index in range(10):
        with SessionLocal() as db:
            peer_org = Organization(name=f"private-peer-{index}", kind="artist")
            db.add(peer_org)
            db.flush()
            peer = Artist(
                organization_id=peer_org.id,
                name=f"private-artist-{index}",
                city="Москва",
                category="dj",
            )
            db.add(peer)
            db.flush()
            peer_ids.append(peer.id)
            db.commit()
        result = client.get(route, headers=headers)
        benchmark = result.json()["benchmark"]
        if index < 9:
            assert benchmark["status"] == "insufficient"
        else:
            assert benchmark["status"] == "available"
            assert benchmark["median_requests"] == 0
            assert "private-" not in result.text
            assert all(peer_id not in result.text for peer_id in peer_ids)


def test_busy_overlay_does_not_hide_another_profiles_free_dates(client):
    _, headers, org = org_user(client)
    first = create_profile(client, headers, org, "Первый")
    second = create_profile(client, headers, org, "Второй")
    start = (now() + timedelta(days=10)).replace(hour=22, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)
    for artist in (first, second):
        assert (
            client.post(
                "/slots",
                headers=headers,
                json={
                    "resource_type": "artist",
                    "resource_id": artist,
                    "starts_at": start.isoformat(),
                    "ends_at": end.isoformat(),
                },
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/calendar/vacation",
            headers=headers,
            json={
                "organization_id": org,
                "resource_type": "artist",
                "resource_id": first,
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
            },
        ).status_code
        == 200
    )
    assert (
        client.get(f"/organizations/{org}/growth?target_id={first}", headers=headers).json()[
            "open_dates"
        ]
        == []
    )
    assert client.get(f"/organizations/{org}/growth", headers=headers).json()["open_dates"] == [
        start.astimezone(MSK).date().isoformat()
    ]
