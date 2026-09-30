import json
from datetime import timedelta

import pytest

from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    Booking,
    BriefResponse,
    Offer,
    OpportunityDelivery,
    PublicBrief,
    Subscription,
)
from booker_api.opportunities import on_brief_published
from booker_api.security import now
from tests.test_commerce import org_user
from tests.test_growth import create_profile, grant


@pytest.fixture()
def parties(client):
    _, headers, org = org_user(client)
    artist = create_profile(client, headers, org)
    start = (now() + timedelta(days=20)).replace(hour=18, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=3)
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
            f"/artists/{artist}/tariffs",
            headers=headers,
            json={"title": "Сет", "honorarium_rub": 20000},
        ).status_code
        == 200
    )
    _, customer, customer_org = org_user(client, kind="customer", suffix="buyer")
    return {
        "headers": headers,
        "org": org,
        "artist": artist,
        "customer": customer,
        "customer_org": customer_org,
        "start": start,
        "end": end,
    }


def publish(client, parties, **changes):
    body = {
        "organization_id": parties["customer_org"],
        "title": "Корпоратив",
        "event_type": "corporate",
        "city": "Москва",
        "date_from": parties["start"].isoformat(),
        "date_to": parties["end"].isoformat(),
        "role_needed": "dj",
        "guest_count_band": "51-100",
        **changes,
    }
    return client.post("/briefs", headers=parties["customer"], json=body)


def get_feed(client, parties, **query):
    result = client.get(
        f"/organizations/{parties['org']}/opportunities", headers=parties["headers"], params=query
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_free_matching_is_explainable_and_same_after_upgrade(client, SessionLocal, parties):
    assert publish(client, parties).status_code == 200
    basic = get_feed(client, parties)
    assert len(basic["items"]) == 1
    item = basic["items"][0]
    assert item["match"]["score"] == 75
    assert item["budget_range"] is None
    assert [r["state"] for r in item["match"]["reasons"]] == [
        "match",
        "match",
        "match",
        "unknown",
        "unknown",
    ]
    grant(SessionLocal, parties["org"], "artist_pro")
    assert get_feed(client, parties)["items"] == basic["items"]
    response = client.post(
        f"/briefs/{item['id']}/responses",
        headers=parties["headers"],
        json={
            "supplier_org_id": parties["org"],
            "message": "Готов обсудить программу",
            "target_type": "artist",
            "target_id": parties["artist"],
        },
    )
    assert response.status_code == 200, response.text
    assert get_feed(client, parties)["items"][0]["response_id"] == response.json()["id"]
    with SessionLocal() as db:
        assert db.query(BriefResponse).count() == 1
        assert db.query(Offer).count() == db.query(Booking).count() == 0


def test_strict_category_city_calendar_and_explicit_budget(client, parties):
    publish(client, parties, role_needed="host")
    publish(client, parties, city="Казань")
    publish(client, parties, share_budget=True, budget_min_rub=1000, budget_max_rub=10000)
    publish(
        client,
        parties,
        date_from=(parties["start"] - timedelta(hours=6)).isoformat(),
        date_to=(parties["start"] - timedelta(hours=4)).isoformat(),
    )
    assert get_feed(client, parties)["items"] == []
    publish(client, parties, share_budget=True, budget_min_rub=15000, budget_max_rub=25000)
    assert get_feed(client, parties)["items"][0]["match"]["score"] == 90
    assert (
        client.post(
            "/calendar/vacation",
            headers=parties["headers"],
            json={
                "organization_id": parties["org"],
                "resource_type": "artist",
                "resource_id": parties["artist"],
                "starts_at": parties["start"].isoformat(),
                "ends_at": parties["end"].isoformat(),
            },
        ).status_code
        == 200
    )
    assert get_feed(client, parties)["items"] == []


def test_private_event_budget_never_leaks_and_public_budget_requires_consent(client, parties):
    event = client.post(
        "/events",
        headers=parties["customer"],
        json={
            "organization_id": parties["customer_org"],
            "title": "Секретное событие",
            "event_date": parties["start"].isoformat(),
            "budget_rub": 999999,
        },
    ).json()
    response = publish(client, parties, event_id=event["id"])
    assert response.status_code == 200
    assert response.json()["budget_range"] is None
    assert "999999" not in response.text and "event_id" not in response.json()
    assert "999999" not in json.dumps(get_feed(client, parties))
    assert publish(client, parties, budget_min_rub=100, budget_max_rub=200).status_code == 422
    assert (
        publish(
            client, parties, share_budget=True, budget_min_rub=300, budget_max_rub=200
        ).status_code
        == 422
    )
    assert (
        publish(
            client, parties, share_budget=True, budget_min_rub=100, budget_max_rub=200
        ).status_code
        == 200
    )


def test_paid_filters_are_enforced_on_server_and_foreign_data_denied(
    client, SessionLocal, parties, monkeypatch
):
    route = f"/organizations/{parties['org']}/opportunities"
    assert (
        client.get(route, headers=parties["headers"], params={"city": "Москва"}).status_code == 403
    )
    _, other, other_org = org_user(client, suffix="outside")
    foreign = create_profile(client, other, other_org)
    assert client.get(route, headers=other).status_code == 403
    assert (
        client.get(route, headers=parties["headers"], params={"target_id": foreign}).status_code
        == 403
    )
    grant(SessionLocal, parties["org"], "artist_pro")
    assert get_feed(client, parties, city="Москва")["items"] == []
    assert (
        client.get(route, headers=parties["headers"], params={"minimum_score": 101}).status_code
        == 422
    )
    assert (
        client.get(
            route,
            headers=parties["headers"],
            params={"date_from": "2026-11-01", "date_to": "2026-10-01"},
        ).status_code
        == 422
    )
    monkeypatch.setattr(settings, "opportunities", False)
    assert client.get(route, headers=parties["headers"]).status_code == 404


def test_saved_filter_consent_idempotency_alerts_expiry_and_removal(client, SessionLocal, parties):
    route = f"/organizations/{parties['org']}/opportunity-filters"
    body = {
        "name": "Корпоративы",
        "query": {"city": "Москва"},
        "instant_alerts": True,
        "consent": True,
        "idempotency_key": "saved-one",
    }
    assert client.post(route, headers=parties["headers"], json=body).status_code == 403
    grant(SessionLocal, parties["org"], "artist_pro")
    assert (
        client.post(route, headers=parties["headers"], json={**body, "consent": False}).status_code
        == 422
    )
    first = client.post(route, headers=parties["headers"], json=body)
    assert first.status_code == 200, first.text
    assert (
        client.post(route, headers=parties["headers"], json=body).json()["id"] == first.json()["id"]
    )
    brief = publish(client, parties).json()
    with SessionLocal() as db:
        on_brief_published(db, db.get(PublicBrief, brief["id"]))
        db.commit()
        assert db.query(OpportunityDelivery).count() == 1
        logs = (
            db.query(AuditLog).filter_by(action="notification.in_app", entity_id=brief["id"]).all()
        )
        assert len(logs) == 1 and json.loads(logs[0].payload)["template"] == "opportunity.matched"
        assert (
            db.query(AuditLog).filter_by(action="notification.email", entity_id=brief["id"]).count()
            == 0
        )
        db.query(Subscription).filter_by(
            organization_id=parties["org"]
        ).first().current_period_end = now() - timedelta(seconds=1)
        db.commit()
    publish(client, parties, title="После окончания тарифа")
    with SessionLocal() as db:
        assert db.query(OpportunityDelivery).count() == 1
    assert (
        client.delete(
            f"/opportunity-filters/{first.json()['id']}", headers=parties["headers"]
        ).status_code
        == 200
    )
    assert client.get(route, headers=parties["headers"]).json()["items"] == []


def test_venue_capacity_band_and_owner_calendar_are_mandatory(client, SessionLocal):
    from booker_api.models import Venue

    _, headers, org = org_user(client, kind="venue", suffix="hall")
    venue = client.post(
        "/venues",
        headers=headers,
        json={"organization_id": org, "name": "Камерный зал", "city": "Москва", "capacity": 80},
    ).json()
    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        row.moderation_status = "published"
        row.is_claimed = True
        row.availability_mode = "owner"
        db.commit()
    hall = client.get(f"/venues/{venue['id']}/halls", headers=headers).json()["items"][0]
    start = now() + timedelta(days=20)
    end = start + timedelta(hours=3)
    assert (
        client.post(
            "/slots",
            headers=headers,
            json={
                "resource_type": "hall",
                "resource_id": hall["id"],
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
            },
        ).status_code
        == 200
    )
    _, customer, customer_org = org_user(client, kind="customer", suffix="venue-buyer")
    parties = {
        "headers": headers,
        "org": org,
        "customer": customer,
        "customer_org": customer_org,
        "start": start,
        "end": end,
    }
    publish(client, parties, role_needed="venue", guest_count_band="200+")
    publish(client, parties, role_needed="venue", guest_count_band="51-100")
    assert get_feed(client, parties)["items"] == []
    publish(client, parties, role_needed="venue", guest_count_band="1-50")
    assert len(get_feed(client, parties)["items"]) == 1
    with SessionLocal() as db:
        db.get(Venue, venue["id"]).availability_mode = "synthetic"
        db.commit()
    assert get_feed(client, parties)["items"] == []
