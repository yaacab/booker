from datetime import timedelta

import pytest

from booker_api.models import (
    Artist,
    AvailabilitySlot,
    HallTechnicalProfile,
    Subscription,
    TeamMember,
    Venue,
)
from booker_api.security import now
from tests.conftest import auth_header, register


def setup_pair(client):
    owner = register(client, "compat-owner@booker.test")
    artist_org = client.post("/orgs", json={"name": "Артист", "kind": "artist"}, headers=auth_header(owner["token"])).json()
    venue_org = client.post("/orgs", json={"name": "Зал", "kind": "venue"}, headers=auth_header(owner["token"])).json()
    artist = client.post("/artists", json={"organization_id": artist_org["id"], "name": "DJ", "category": "dj"}, headers=auth_header(owner["token"])).json()
    venue = client.post("/venues", json={"organization_id": venue_org["id"], "name": "Сцена", "capacity": 120}, headers=auth_header(owner["token"])).json()
    start = now().replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=15)
    end = start + timedelta(hours=3)
    for kind, resource in [("artist", artist["id"]), ("hall", venue["hall_id"])]:
        res = client.post("/slots", json={"resource_type": kind, "resource_id": resource, "starts_at": (start-timedelta(hours=1)).isoformat(), "ends_at": (end+timedelta(hours=1)).isoformat()}, headers=auth_header(owner["token"]))
        assert res.status_code == 200, res.text
    return {"owner": owner, "artist_org": artist_org, "venue_org": venue_org, "artist": artist, "venue": venue,
            "query": {"artist_id": artist["id"], "venue_id": venue["id"], "hall_id": venue["hall_id"], "starts_at": start.isoformat(), "ends_at": end.isoformat(), "guest_count": 100}}


def fill_facts(client, ctx):
    headers = auth_header(ctx["owner"]["token"])
    editor = client.get(f"/artists/{ctx['artist']['id']}/presentation", headers=headers).json()
    artist_data = {**editor["data"], "expected_version": editor["version"], "technical": {"stage_area_m2": 12, "power_kw": 3, "basic_sound": True, "microphones": 2, "setup_minutes": 30, "teardown_minutes": 20, "required_equipment": ["DJM-900", "Монитор"], "supplied_equipment": ["Монитор"]}}
    res = client.put(f"/artists/{ctx['artist']['id']}/presentation", json=artist_data, headers=headers)
    assert res.status_code == 200, res.text
    data = {"capacity": 120, "stage_area_m2": 20, "power_kw": 5, "basic_sound": True, "microphones": 3, "equipment": ["djm-900"], "restrictions": "", "expected_version": 0}
    res = client.put(f"/halls/{ctx['venue']['hall_id']}/technical", json=data, headers=headers)
    assert res.status_code == 200, res.text
    return data


def test_unknown_is_not_compatible_and_complete_facts_are_explainable(client, SessionLocal):
    ctx = setup_pair(client)
    before = client.post("/compatibility", json=ctx["query"])
    assert before.status_code == 200, before.text
    result = before.json()
    assert result["status"] == "attention" and result["score"] < 100
    assert any(c["status"] == "unknown" for c in result["checks"])
    fill_facts(client, ctx)
    after = client.post("/compatibility", json=ctx["query"]).json()
    assert after["status"] == "compatible" and after["score"] == 100
    assert after["to_resolve"] == [] and after["missing_required_items"] == []
    assert len(after["checks"]) == 10
    with SessionLocal() as db:
        db.add(Subscription(organization_id=ctx["artist_org"]["id"], plan_code="artist_premium", starts_at=now()-timedelta(days=1), current_period_end=now()+timedelta(days=30), status="active", billing_period="monthly"))
        db.commit()
    assert client.post("/compatibility", json=ctx["query"]).json() == after


def test_missing_console_capacity_and_busy_buffer_are_not_overridden(client, SessionLocal):
    ctx = setup_pair(client)
    data = fill_facts(client, ctx)
    data.update(expected_version=1, capacity=80, equipment=[])
    assert client.put(f"/halls/{ctx['venue']['hall_id']}/technical", json=data, headers=auth_header(ctx["owner"]["token"])).status_code == 200
    result = client.post("/compatibility", json=ctx["query"]).json()
    assert result["status"] == "incompatible"
    assert result["missing_required_items"] == ["DJM-900"]  # monitor is brought by artist
    assert {c["code"] for c in result["to_resolve"]} == {"capacity", "equipment"}
    from datetime import datetime
    start = datetime.fromisoformat(ctx["query"]["starts_at"])
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type="hall", resource_id=ctx["venue"]["hall_id"], starts_at=start-timedelta(minutes=25), ends_at=start-timedelta(minutes=10), status="busy"))
        db.commit()
    checks = {c["code"]: c for c in client.post("/compatibility", json=ctx["query"]).json()["checks"]}
    assert checks["date"]["status"] == "compatible"
    assert checks["buffers"]["status"] == "incompatible"


def test_technical_writer_idor_versions_and_venue_scope(client, SessionLocal):
    ctx = setup_pair(client)
    viewer = register(client, "compat-viewer@booker.test")
    outsider = register(client, "compat-outsider@booker.test")
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx["venue_org"]["id"], user_id=viewer["user_id"], role="viewer")); db.commit()
    path = f"/halls/{ctx['venue']['hall_id']}/technical"
    original = client.get(path, headers=auth_header(ctx["owner"]["token"])).json()
    data = {**original["data"], "expected_version": original["version"], "capacity": 150}
    assert client.get(path, headers=auth_header(outsider["token"])).status_code == 403
    assert client.get(path, headers=auth_header(viewer["token"])).status_code == 200
    for user in [outsider, viewer]:
        assert client.put(path, json=data, headers=auth_header(user["token"])).status_code == 403
    headers = auth_header(ctx["owner"]["token"])
    assert client.put(path, json=data, headers=headers).status_code == 200
    assert client.put(path, json=data, headers=headers).json()["idempotent"] is True
    assert client.put(path, json={**data, "capacity": 160}, headers=headers).status_code == 409
    with SessionLocal() as db:
        assert db.get(Venue, ctx["venue"]["id"]).capacity == 150
        assert db.query(HallTechnicalProfile).count() == 1
        assert not db.get(Artist, ctx["artist"]["id"]).verified


def test_private_event_and_unpublished_venue_are_protected(client, SessionLocal):
    ctx = setup_pair(client)
    customer = register(client, "compat-customer@booker.test")
    customer_org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=auth_header(customer["token"])).json()
    event = client.post("/events", json={"organization_id": customer_org["id"], "title": "Приватно", "event_date": ctx["query"]["starts_at"], "guest_count": 200}, headers=auth_header(customer["token"])).json()
    query = {**ctx["query"], "event_id": event["id"], "guest_count": 1}
    assert client.post("/compatibility", json=query).status_code == 401
    assert client.post("/compatibility", json=query, headers=auth_header(ctx["owner"]["token"])).status_code == 403
    result = client.post("/compatibility", json=query, headers=auth_header(customer["token"])).json()
    assert result["guest_count"] == 200
    assert next(c for c in result["checks"] if c["code"] == "capacity")["status"] == "incompatible"
    with SessionLocal() as db:
        db.get(Venue, ctx["venue"]["id"]).moderation_status = "needs_review"; db.commit()
    assert client.post("/compatibility", json=ctx["query"]).status_code == 404
    assert client.post("/compatibility", json=ctx["query"], headers=auth_header(ctx["owner"]["token"])).status_code == 200


def test_synthetic_calendar_and_unspecified_hall_remain_unknown(client, SessionLocal, monkeypatch):
    ctx = setup_pair(client)
    fill_facts(client, ctx)
    with SessionLocal() as db:
        venue = db.get(Venue, ctx["venue"]["id"]); venue.availability_mode = "synthetic"; venue.is_claimed = False; db.commit()
    result = client.post("/compatibility", json=ctx["query"]).json()
    assert result["status"] != "compatible"
    assert next(c for c in result["checks"] if c["code"] == "date")["status"] == "unknown"
    assert client.post("/compatibility", json={**ctx["query"], "hall_id": ctx["artist"]["id"]}).status_code == 404
    from booker_api.config import settings
    monkeypatch.setattr(settings, "compatibility", False)
    assert client.post("/compatibility", json=ctx["query"]).status_code == 503


@pytest.mark.parametrize("guest_count", [-1, True, 1.5])
def test_compatibility_inputs_are_typed(client, guest_count):
    ctx = setup_pair(client)
    assert client.post("/compatibility", json={**ctx["query"], "guest_count": guest_count}).status_code == 422


def test_event_can_use_its_own_hold_but_public_check_cannot(client, SessionLocal):
    ctx = setup_pair(client)
    fill_facts(client, ctx)
    customer = register(client, "own-hold-customer@booker.test")
    headers = auth_header(customer["token"])
    org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=headers).json()
    event = client.post("/events", json={"organization_id": org["id"], "title": "Событие", "event_date": ctx["query"]["starts_at"], "guest_count": 100}, headers=headers).json()
    req = client.post(f"/events/{event['id']}/requests", json={"resource_type": "artist", "resource_id": ctx["artist"]["id"]}, headers=headers).json()
    with SessionLocal() as db:
        slot_id = db.query(AvailabilitySlot).filter_by(resource_type="artist", resource_id=ctx["artist"]["id"]).one().id
    offer = client.post(f"/requests/{req['id']}/offers", json={"honorarium_rub": 100000, "slot_id": slot_id}, headers=auth_header(ctx["owner"]["token"])).json()
    for side, token in [("customer", customer["token"]), ("supplier", ctx["owner"]["token"])]:
        assert client.post(f"/offers/{offer['id']}/ack", json={"side": side}, headers=auth_header(token)).status_code == 200
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=headers).status_code == 200
    assert client.post("/compatibility", json=ctx["query"]).json()["status"] == "incompatible"
    event_query = {**ctx["query"], "event_id": event["id"]}
    assert client.post("/compatibility", json=event_query, headers=headers).json()["status"] == "compatible"
    assert client.post("/compatibility", json={**ctx["query"], "own_slot_ids": [slot_id]}).status_code == 422
    from booker_api.models import BookingHold
    with SessionLocal() as db:
        db.query(BookingHold).filter_by(booking_id=offer["booking_id"]).one().expires_at = now()-timedelta(seconds=1)
        db.commit()
    assert client.post("/compatibility", json=event_query, headers=headers).json()["status"] == "incompatible"


def test_multiple_halls_require_explicit_choice(client):
    ctx = setup_pair(client)
    fill_facts(client, ctx)
    assert client.post(f"/venues/{ctx['venue']['id']}/halls", json={"name": "Малый зал", "capacity": 20}, headers=auth_header(ctx["owner"]["token"])).status_code == 200
    query = {k: v for k, v in ctx["query"].items() if k != "hall_id"}
    result = client.post("/compatibility", json=query).json()
    assert result["hall"] is None and len(result["halls"]) == 2
    assert next(c for c in result["checks"] if c["code"] == "date")["status"] == "unknown"
