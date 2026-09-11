from datetime import datetime, timezone

from booker_api.config import settings
from tests.conftest import auth_header
from tests.test_calendar import _owner_artist
from tests.test_offers import setup_negotiation, ack_both


def test_moscow_slot_roundtrip_and_equivalent_utc_overlap(client, engine):
    owner, artist = _owner_artist(client)
    payload = {"resource_type": "artist", "resource_id": artist["id"],
               "starts_at": "2026-12-02T18:00:00+03:00", "ends_at": "2026-12-02T22:00:00+03:00"}
    saved = client.post("/slots", json=payload, headers=auth_header(owner["token"]))
    assert saved.status_code == 200, saved.text
    profile = client.get(f"/artists/{artist['id']}").json()
    slot = profile["slots"][0]
    assert slot["starts_at"] == "2026-12-02T18:00:00+03:00"
    with engine.connect() as conn:
        raw = conn.exec_driver_sql("select starts_at from availability_slots").scalar_one()
    assert str(raw).startswith("2026-12-02 15:00:00")
    clash = client.post("/slots", json={**payload, "starts_at": "2026-12-02T15:30:00Z", "ends_at": "2026-12-02T16:00:00Z"}, headers=auth_header(owner["token"]))
    assert clash.status_code == 409


def test_event_and_brief_keep_offset_after_sqlite_roundtrip(client):
    ctx = setup_negotiation(client)
    headers = auth_header(ctx["customer"]["token"])
    event = client.post("/events", json={"organization_id": ctx["cust_org"]["id"], "title": "Вечер по Москве", "event_date": "2026-12-02T18:00:00+03:00"}, headers=headers).json()
    read = client.get(f"/events/{event['id']}", headers=headers).json()
    assert datetime.fromisoformat(read["event_date"]) == datetime(2026, 12, 2, 15, tzinfo=timezone.utc)
    brief = client.post("/briefs", json={"organization_id": ctx["cust_org"]["id"], "title": "Артист на вечер", "role_needed": "dj", "date_from": "2026-12-02T18:00:00+03:00", "date_to": "2026-12-02T22:00:00+03:00"}, headers=headers)
    assert brief.status_code == 200
    assert datetime.fromisoformat(brief.json()["date_from"]) == datetime(2026, 12, 2, 15, tzinfo=timezone.utc)


def test_hold_deadline_is_real_utc_duration_and_shared(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    before = datetime.now(timezone.utc)
    held = client.post(f"/bookings/{ctx['booking_id']}/hold", headers=auth_header(ctx["customer"]["token"]))
    assert held.status_code == 200
    deadline = datetime.fromisoformat(held.json()["expires_at"])
    assert deadline.tzinfo is not None
    assert abs((deadline-before).total_seconds()-settings.hold_ttl_hours*3600) < 10
    for party in (ctx["customer"], ctx["owner"]):
        room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(party["token"])).json()
        assert datetime.fromisoformat(room["hold"]["expires_at"]) == deadline
