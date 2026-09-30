from datetime import timedelta

from booker_api.models import (
    AuditLog,
    AvailabilitySlot,
    Booking,
    EventPlan,
    Offer,
    Request,
    Subscription,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import activate_venue, auth_header, register


def setup_matching(client):
    owner = register(client, "matching-owner@booker.test")
    headers = auth_header(owner["token"])
    customer = client.post("/orgs", headers=headers, json={"name": "Заказчик", "kind": "customer"}).json()
    supply = client.post("/orgs", headers=headers, json={"name": "Команда", "kind": "artist"}).json()
    venue_org = client.post("/orgs", headers=headers, json={"name": "Зал", "kind": "venue"}).json()
    start = now().replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=20)
    end = start + timedelta(hours=3)
    event = client.post("/events", headers=headers, json={"organization_id": customer["id"], "title": "Корпоратив", "event_date": start.isoformat(), "ends_at": end.isoformat(), "budget_rub": 250000, "guest_count": 100,
        "requirements": [{"category_code": "dj"}, {"category_code": "venue"}, {"category_code": "photo", "required": False}]}).json()
    tech = {"stage_area_m2": 12, "power_kw": 3, "basic_sound": True, "microphones": 2, "setup_minutes": 30, "teardown_minutes": 20, "required_equipment": ["CDJ"], "supplied_equipment": []}
    artists = []
    for name, price, category, technical, rich in [("Доступный", 60000, "dj", None, False), ("Все условия", 90000, "dj", tech, False), ("Подробная программа", 120000, "dj", tech, True), ("Фотограф", 30000, "photo", tech, True)]:
        artist = client.post("/artists", headers=headers, json={"organization_id": supply["id"], "name": name, "category": category}).json()
        artists.append(artist)
        assert client.post(f"/artists/{artist['id']}/tariffs", headers=headers, json={"title": "Пакет", "honorarium_rub": price, "hours": 3}).status_code == 200
        if technical:
            data = client.get(f"/artists/{artist['id']}/presentation", headers=headers).json()
            changed = {**data["data"], "technical": technical, "expected_version": data["version"]}
            if rich:
                changed.update(program="Программа на вечер", format="Корпоратив", lineup="Два участника")
            assert client.put(f"/artists/{artist['id']}/presentation", headers=headers, json=changed).status_code == 200
        assert client.post("/slots", headers=headers, json={"resource_type": "artist", "resource_id": artist["id"], "starts_at": (start-timedelta(hours=1)).isoformat(), "ends_at": (end+timedelta(hours=1)).isoformat()}).status_code == 200
    venue = client.post("/venues", headers=headers, json={"organization_id": venue_org["id"], "name": "Зал", "capacity": 150}).json()
    assert client.post(f"/venues/{venue['id']}/tariffs", headers=headers, json={"title": "Аренда", "honorarium_rub": 100000}).status_code == 200
    assert client.post("/slots", headers=headers, json={"resource_type": "hall", "resource_id": venue["hall_id"], "starts_at": (start-timedelta(hours=1)).isoformat(), "ends_at": (end+timedelta(hours=1)).isoformat()}).status_code == 200
    assert client.put(f"/halls/{venue['hall_id']}/technical", headers=headers, json={"expected_version": 0, "capacity": 150, "stage_area_m2": 20, "power_kw": 5, "basic_sound": True, "microphones": 3, "equipment": ["CDJ"], "restrictions": ""}).status_code == 200
    activate_venue(client, venue["id"])
    return {"headers": headers, "owner": owner, "customer": customer, "supply": supply, "venue": venue, "artists": artists, "event": event, "start": start, "end": end, "path": f"/events/{event['id']}/matching"}


def save_payload(result, variant=0):
    return {"expected_revision": result["revision"], "expected_context": result["context_token"],
            "selections": [{k: item.get(k) for k in ("requirement_id", "position", "resource_type", "resource_id", "hall_id")} for item in result["variants"][variant]["selections"]]}


def test_three_variants_are_factual_and_subscription_independent(client, SessionLocal):
    ctx = setup_matching(client)
    response = client.get(ctx["path"], headers=ctx["headers"])
    assert response.status_code == 200, response.text
    result = response.json()
    variants = result["variants"]
    assert [v["title"] for v in variants] == ["Экономный", "Оптимальный", "Расширенный"]
    assert [next(i["resource_id"] for i in v["selections"] if i["category"] == "dj") for v in variants] == [a["id"] for a in ctx["artists"][:3]]
    assert [v["orientation"]["min_rub"] for v in variants] == [160000, 190000, 250000]
    assert variants[2]["optional_covered"] == 1 and variants[0]["optional_covered"] == 0
    assert all(v["required_total"] == v["required_covered"] == 2 for v in variants)
    assert variants[0]["selections"][-1]["warnings"]
    assert not result["variants_overlap"]
    with SessionLocal() as db:
        assert db.query(Offer).count() == db.query(Booking).count() == db.query(Request).count() == 0
        db.add(Subscription(organization_id=ctx["supply"]["id"], plan_code="artist_premium", billing_period="monthly", status="active", starts_at=now(), current_period_end=now()+timedelta(days=30))); db.commit()
    after = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert after == result


def test_save_replace_replay_and_optimistic_conflict_do_not_create_deals(client, SessionLocal):
    ctx = setup_matching(client)
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    data = save_payload(result)
    path = f"/events/{ctx['event']['id']}/plan"
    saved = client.put(path, headers=ctx["headers"], json=data)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert client.put(path, headers=ctx["headers"], json=data).json()["reused"]
    assert client.put(path, headers=ctx["headers"], json=save_payload(result, 1)).status_code == 409
    changed = client.put(path, headers=ctx["headers"], json=save_payload(saved.json(), 1)).json()
    assert changed["revision"] == 2 and changed["current"]["orientation"]["min_rub"] == 190000
    with SessionLocal() as db:
        assert db.query(EventPlan).count() == 1
        assert db.query(AuditLog).filter_by(action="event.plan_updated").count() == 2
        assert db.query(Offer).count() == db.query(Booking).count() == db.query(Request).count() == 0


def test_busy_calendar_full_window_and_known_incompatibility_are_excluded(client, SessionLocal):
    ctx = setup_matching(client)
    with SessionLocal() as db:
        # A busy overlay affecting only the setup window disqualifies the otherwise known match.
        db.add(AvailabilitySlot(resource_type="artist", resource_id=ctx["artists"][1]["id"], starts_at=ctx["start"]-timedelta(minutes=25), ends_at=ctx["start"]-timedelta(minutes=10), status="busy"))
        slot = db.query(AvailabilitySlot).filter_by(resource_id=ctx["artists"][0]["id"]).one(); slot.ends_at = ctx["end"]-timedelta(minutes=1)
        db.commit()
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert {i["resource_id"] for i in result["candidates"]["dj"]} == {ctx["artists"][2]["id"]}
    hall_path = f"/halls/{ctx['venue']['hall_id']}/technical"
    hall = client.get(hall_path, headers=ctx["headers"]).json()
    assert client.put(hall_path, headers=ctx["headers"], json={**hall["data"], "expected_version": hall["version"], "equipment": []}).status_code == 200
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert all(not any(i["resource_type"] == "artist" for i in v["selections"]) for v in result["variants"])
    assert all(v["required_covered"] < v["required_total"] for v in result["variants"])


def test_membership_viewer_context_and_flag(client, SessionLocal, monkeypatch):
    ctx = setup_matching(client)
    outsider = register(client, "matching-outsider@booker.test")
    viewer = register(client, "matching-viewer@booker.test")
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx["customer"]["id"], user_id=viewer["user_id"], role="viewer")); db.commit()
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    path = f"/events/{ctx['event']['id']}/plan"
    assert client.get(ctx["path"], headers=auth_header(outsider["token"])).status_code == 403
    assert client.put(path, headers=auth_header(viewer["token"]), json=save_payload(result)).status_code == 403
    assert not client.get(ctx["path"], headers=auth_header(viewer["token"])).json()["can_manage"]
    client.put(f"/events/{ctx['event']['id']}/requirements", headers=ctx["headers"], json={"items": [{"category_code": "dj", "qty": 2}]})
    assert client.put(path, headers=ctx["headers"], json=save_payload(result)).status_code == 409
    from booker_api.config import settings
    monkeypatch.setattr(settings, "smart_matching", False)
    assert client.get(ctx["path"], headers=ctx["headers"]).status_code == 503


def test_saved_candidate_is_revalidated_after_calendar_changes(client, SessionLocal):
    ctx = setup_matching(client)
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type="artist", resource_id=ctx["artists"][0]["id"], starts_at=ctx["start"], ends_at=ctx["end"], status="busy")); db.commit()
    assert client.put(f"/events/{ctx['event']['id']}/plan", headers=ctx["headers"], json=save_payload(result)).status_code == 409
    data = save_payload(client.get(ctx["path"], headers=ctx["headers"]).json())
    data["selections"][0]["price_rub"] = 1
    assert client.put(f"/events/{ctx['event']['id']}/plan", headers=ctx["headers"], json=data).status_code == 422


def test_planning_context_unknown_window_and_budget(client, SessionLocal):
    from booker_api.models import Event
    ctx = setup_matching(client)
    with SessionLocal() as db:
        db.get(Event, ctx["event"]["id"]).ends_at = None; db.commit()
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert result["state"] == "needs_window" and all(v["selections"] == [] for v in result["variants"])
    updated = client.patch(f"/events/{ctx['event']['id']}/planning-context", headers=ctx["headers"], json={"expected_context": result["context_token"], "ends_at": ctx["end"].isoformat(), "budget_rub": 300000})
    assert updated.status_code == 200, updated.text
    assert updated.json()["state"] == "ready" and updated.json()["declared_budget"] == 300000


def test_own_live_hold_is_available_only_to_this_event_and_end_is_locked(client, SessionLocal):
    ctx = setup_matching(client)
    headers = ctx["headers"]
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=headers, json={"resource_type": "artist", "resource_id": ctx["artists"][1]["id"], "requirement_id": ctx["event"]["requirements"][0]["id"]}).json()
    with SessionLocal() as db:
        slot_id = db.query(AvailabilitySlot).filter_by(resource_id=ctx["artists"][1]["id"]).one().id
    offer = client.post(f"/requests/{req['id']}/offers", headers=headers, json={"honorarium_rub": 90000, "slot_id": slot_id}).json()
    for side in ["customer", "supplier"]:
        assert client.post(f"/offers/{offer['id']}/ack", headers=headers, json={"side": side}).status_code == 200
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=headers).status_code == 200
    result = client.get(ctx["path"], headers=headers).json()
    assert ctx["artists"][1]["id"] in {i["resource_id"] for i in result["candidates"]["dj"]}
    assert not result["can_adjust_end"]
    path = f"/events/{ctx['event']['id']}/planning-context"
    assert client.patch(path, headers=headers, json={"expected_context": result["context_token"], "ends_at": (ctx["end"]+timedelta(hours=1)).isoformat()}).status_code == 409
    assert client.patch(path, headers=headers, json={"expected_context": result["context_token"], "budget_rub": 500000}).status_code == 200
    with SessionLocal() as db:
        from booker_api.models import OfferVersion
        version = db.get(OfferVersion, offer["version"]["quote_id"])
        assert version.total_rub == offer["version"]["total_rub"]
    second = client.post("/events", headers=headers, json={"organization_id": ctx["customer"]["id"], "title": "Другое событие", "event_date": ctx["start"].isoformat(), "ends_at": ctx["end"].isoformat(), "requirements": [{"category_code": "dj"}]}).json()
    other = client.get(f"/events/{second['id']}/matching", headers=headers).json()
    assert ctx["artists"][1]["id"] not in {i["resource_id"] for i in other["candidates"]["dj"]}


def test_several_halls_are_distinct_but_their_package_cost_is_not_invented(client):
    ctx = setup_matching(client)
    headers = ctx["headers"]
    hall = client.post(f"/venues/{ctx['venue']['id']}/halls", headers=headers, json={"name": "Второй зал", "capacity": 110}).json()
    assert client.post("/slots", headers=headers, json={"resource_type": "hall", "resource_id": hall["id"], "starts_at": ctx["start"].isoformat(), "ends_at": ctx["end"].isoformat()}).status_code == 200
    assert client.put(f"/events/{ctx['event']['id']}/requirements", headers=headers, json={"items": [{"category_code": "venue", "qty": 2}]}).status_code == 200
    result = client.get(ctx["path"], headers=headers).json()
    for variant in result["variants"]:
        assert len({i["hall_id"] for i in variant["selections"]}) == 2
        assert variant["orientation"]["min_rub"] is None and variant["orientation"]["state"] == "unknown"
    data = save_payload(result)
    assert client.put(f"/events/{ctx['event']['id']}/plan", headers=headers, json=data).status_code == 200


def test_unclaimed_or_hidden_venue_cannot_be_used_after_save(client, SessionLocal):
    from booker_api.models import Venue
    ctx = setup_matching(client)
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert client.put(f"/events/{ctx['event']['id']}/plan", headers=ctx["headers"], json=save_payload(result)).status_code == 200
    with SessionLocal() as db:
        venue = db.get(Venue, ctx["venue"]["id"]); venue.is_claimed = False; venue.availability_mode = "synthetic"; db.commit()
    result = client.get(ctx["path"], headers=ctx["headers"]).json()
    assert result["current"]["problems"]
    assert all(not any(i["resource_type"] == "venue" for i in v["selections"]) for v in result["variants"])
    assert all(v["required_covered"] < v["required_total"] for v in result["variants"])
