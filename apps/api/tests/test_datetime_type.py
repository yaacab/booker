from datetime import datetime, timezone

from booker_api.models import AvailabilitySlot
from tests.test_commerce import org_user
from tests.test_growth import create_profile


def test_slot_offset_roundtrip_and_same_instant_collision(client, SessionLocal):
    _, headers, org = org_user(client)
    artist = create_profile(client, headers, org)
    body = {
        "resource_type": "artist",
        "resource_id": artist,
        "starts_at": "2026-12-15T18:00:00+03:00",
        "ends_at": "2026-12-15T21:00:00+03:00",
    }
    first = client.post("/slots", headers=headers, json=body)
    assert first.status_code == 200, first.text
    with SessionLocal() as db:
        slot = db.get(AvailabilitySlot, first.json()["id"])
        assert slot.starts_at == datetime(2026, 12, 15, 15, tzinfo=timezone.utc)
        assert slot.ends_at == datetime(2026, 12, 15, 18, tzinfo=timezone.utc)
    duplicate = client.post(
        "/slots",
        headers=headers,
        json={**body, "starts_at": "2026-12-15T15:00:00Z", "ends_at": "2026-12-15T18:00:00Z"},
    )
    assert duplicate.status_code == 409, duplicate.text
    public = client.get(f"/artists/{artist}").json()["slots"][0]
    assert datetime.fromisoformat(public["starts_at"]) == datetime(
        2026, 12, 15, 15, tzinfo=timezone.utc
    )


def test_busy_overlay_in_another_offset_masks_the_same_instant(client):
    _, headers, org = org_user(client)
    artist = create_profile(client, headers, org)
    client.post(
        "/slots",
        headers=headers,
        json={
            "resource_type": "artist",
            "resource_id": artist,
            "starts_at": "2026-12-15T18:00:00+03:00",
            "ends_at": "2026-12-15T21:00:00+03:00",
        },
    )
    before = client.get(
        "/catalog/search",
        params={"city": "Москва", "date": "2026-12-15T12:00:00Z", "kind": "artist"},
    ).json()
    assert any(i["id"] == artist for i in before["items"])
    busy = client.post(
        "/calendar/vacation",
        headers=headers,
        json={
            "organization_id": org,
            "resource_type": "artist",
            "resource_id": artist,
            "starts_at": "2026-12-15T15:00:00Z",
            "ends_at": "2026-12-15T18:00:00Z",
        },
    )
    assert busy.status_code == 200, busy.text
    after = client.get(
        "/catalog/search",
        params={"city": "Москва", "date": "2026-12-15T12:00:00Z", "kind": "artist"},
    ).json()
    assert all(i["id"] != artist for i in after["items"])
