from tests.conftest import auth_header, register

SAMPLE_ICAL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Booker//Test//EN
BEGIN:VEVENT
UID:gig-1@test
DTSTART:20261005T180000Z
DTEND:20261005T220000Z
SUMMARY:Gig
END:VEVENT
BEGIN:VEVENT
UID:vacation@test
DTSTART;VALUE=DATE:20261010
DTEND;VALUE=DATE:20261012
SUMMARY:Vacation
END:VEVENT
BEGIN:VEVENT
UID:cancelled@test
DTSTART:20261015T120000Z
DTEND:20261015T140000Z
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
            "starts_at": "2026-10-05T19:00:00+00:00",
            "ends_at": "2026-10-05T21:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert open_slot.status_code == 200

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
    assert body["removed_open"] >= 1

    page = client.get(f"/artists/{artist['id']}").json()
    statuses = {s["status"] for s in page["slots"]}
    assert "busy" in statuses
    assert "open" not in statuses

    missing = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "dj", "date": "2026-10-05T12:00:00+00:00"},
    )
    assert missing.json()["items"] == []


def test_ical_reimport_replaces_previous_busy(client):
    owner, org, artist = _artist_ctx(client)
    headers = auth_header(owner["token"])
    payload = {
        "organization_id": org["id"],
        "resource_type": "artist",
        "resource_id": artist["id"],
        "ical_body": SAMPLE_ICAL,
    }
    first = client.post("/calendar/ical/import", json=payload, headers=headers)
    assert first.status_code == 200
    second = client.post("/calendar/ical/import", json=payload, headers=headers)
    assert second.status_code == 200
    page = client.get(f"/artists/{artist['id']}").json()
    busy = [s for s in page["slots"] if s["status"] == "busy"]
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
