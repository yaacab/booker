import json
from datetime import datetime, timedelta, timezone

from booker_api.ical import MAX_ICAL_BYTES
from booker_api.request_body_limit import MULTIPART_OVERHEAD_BYTES
from tests.conftest import auth_header, publish_artist, register

# Dates are relative to "now": publication requires future calendar entries, so
# fixed calendar dates turn these tests red once they pass.
GIG_DAY = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)


def _ymd(offset_days: int = 0) -> str:
    return (GIG_DAY + timedelta(days=offset_days)).strftime("%Y%m%d")


def _iso(hour: int) -> str:
    return GIG_DAY.replace(hour=hour).isoformat()


SAMPLE_ICAL = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Booker//Test//EN
BEGIN:VEVENT
UID:gig-1@test
DTSTART:{_ymd()}T180000Z
DTEND:{_ymd()}T220000Z
SUMMARY:Gig
END:VEVENT
BEGIN:VEVENT
UID:vacation@test
DTSTART;VALUE=DATE:{_ymd(5)}
DTEND;VALUE=DATE:{_ymd(7)}
SUMMARY:Vacation
END:VEVENT
BEGIN:VEVENT
UID:cancelled@test
DTSTART:{_ymd(10)}T120000Z
DTEND:{_ymd(10)}T140000Z
STATUS:CANCELLED
SUMMARY:Cancelled
END:VEVENT
END:VCALENDAR
"""


def _artist_ctx(client):
    owner = register(client, "ical@booker.test", "Ical")
    org = client.post(
        "/orgs",
        json={"name": "DJ Org", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Busy", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, org, artist


def test_calendar_targets_for_artist(client):
    owner, org, artist = _artist_ctx(client)
    res = client.get(
        f"/organizations/{org['id']}/calendar-targets",
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["resource_id"] == artist["id"]
    assert items[0]["resource_type"] == "artist"


def test_ical_import_creates_busy_slots(client):
    owner, org, artist = _artist_ctx(client)
    open_slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": _iso(19),
            "ends_at": _iso(21),
        },
        headers=auth_header(owner["token"]),
    )
    assert open_slot.status_code == 200
    publish_artist(client, owner, artist["id"])

    res = client.post(
        "/calendar/ical/import",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "ical_body": SAMPLE_ICAL,
        },
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 2
    assert body["skipped"] == 1
    assert body["overlaid_open"] >= 1
    assert body["removed_open"] == body["overlaid_open"]

    public = client.get(f"/artists/{artist['id']}").json()
    assert all(slot["status"] == "open" for slot in public["slots"])
    page = client.get(f"/artists/{artist['id']}", headers=auth_header(owner["token"])).json()
    statuses = {s["status"] for s in page["slots"]}
    assert "busy" in statuses
    assert "open" in statuses  # overlay keeps local open slots

    missing = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "dj", "date": _iso(12)},
    )
    assert missing.json()["items"] == []


def test_ical_reimport_preserves_open_under_overlay(client):
    owner, org, artist = _artist_ctx(client)
    headers = auth_header(owner["token"])
    open_slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": _iso(19),
            "ends_at": _iso(21),
        },
        headers=headers,
    )
    assert open_slot.status_code == 200
    publish_artist(client, owner, artist["id"])
    open_id = open_slot.json()["id"]
    payload = {
        "organization_id": org["id"],
        "resource_type": "artist",
        "resource_id": artist["id"],
        "ical_body": SAMPLE_ICAL,
    }
    assert client.post("/calendar/ical/import", json=payload, headers=headers).status_code == 200
    page = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert any(s["id"] == open_id and s["status"] == "open" for s in page["slots"])
    # Reimport replaces only ical:* busy rows
    assert client.post("/calendar/ical/import", json=payload, headers=headers).status_code == 200
    page2 = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert any(s["id"] == open_id and s["status"] == "open" for s in page2["slots"])
    busy = [s for s in page2["slots"] if s["status"] == "busy"]
    assert len(busy) == 2


def test_ical_import_requires_writer(client):
    owner, org, artist = _artist_ctx(client)
    viewer = register(client, "ical-viewer@booker.test", "Viewer")
    client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(owner["token"]),
    )
    res = client.post(
        "/calendar/ical/import",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "ical_body": SAMPLE_ICAL,
        },
        headers=auth_header(viewer["token"]),
    )
    assert res.status_code == 403


def test_ical_inline_body_rejected_before_import_when_oversized(client, SessionLocal):
    owner, org, artist = _artist_ctx(client)
    res = client.post(
        "/calendar/ical/import",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "ical_body": SAMPLE_ICAL + (" " * MAX_ICAL_BYTES),
        },
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 400
    assert "большой" in res.json()["detail"]
    from booker_api.models import AvailabilitySlot

    with SessionLocal() as db:
        assert db.query(AvailabilitySlot).filter_by(resource_type="artist", resource_id=artist["id"]).count() == 0


def test_ical_request_body_rejected_before_json_parse(client):
    limit = MAX_ICAL_BYTES * 6 + MULTIPART_OVERHEAD_BYTES
    res = client.post("/calendar/ical/import", content=b"x" * (limit + 1))
    assert res.status_code == 413
    assert "iCal слишком большой" in res.json()["detail"]


def test_ical_inline_body_rejects_invalid_unicode(client):
    owner, org, artist = _artist_ctx(client)
    payload = json.dumps(
        {
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "ical_body": "BEGIN:VCALENDAR\n" + "\ud800",
        }
    ).encode("utf-8")
    res = client.post(
        "/calendar/ical/import",
        content=payload,
        headers={**auth_header(owner["token"]), "content-type": "application/json"},
    )
    assert res.status_code == 400
