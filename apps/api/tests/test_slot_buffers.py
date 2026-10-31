from tests.conftest import auth_header, register


def _owner_artist(client, email: str):
    owner = register(client, email, "Buf")
    org = client.post(
        "/orgs",
        json={"name": "Буфер", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Кавер", "category": "cover"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, artist


def test_adjacent_slots_ok_without_buffer_conflict_with_after_buffer(client):
    owner, artist = _owner_artist(client, "buf-ok@booker.test")
    first = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-01T18:00:00+00:00",
            "ends_at": "2026-10-01T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert first.status_code == 200, first.text
    adjacent = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-01T22:00:00+00:00",
            "ends_at": "2026-10-01T23:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert adjacent.status_code == 200, adjacent.text

    owner2, artist2 = _owner_artist(client, "buf-clash@booker.test")
    buffered = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist2["id"],
            "starts_at": "2026-10-01T18:00:00+00:00",
            "ends_at": "2026-10-01T22:00:00+00:00",
            "buffer_after_min": 60,
        },
        headers=auth_header(owner2["token"]),
    )
    assert buffered.status_code == 200, buffered.text
    clash = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist2["id"],
            "starts_at": "2026-10-01T22:00:00+00:00",
            "ends_at": "2026-10-01T23:00:00+00:00",
        },
        headers=auth_header(owner2["token"]),
    )
    assert clash.status_code == 409
    page = client.get(f"/artists/{artist2['id']}")
    assert page.status_code == 200
    buffered_row = next(s for s in page.json()["slots"] if s["id"] == buffered.json()["id"])
    assert buffered_row["buffer_after_min"] == 60


def test_negative_slot_buffer_rejected(client):
    owner, artist = _owner_artist(client, "buf-neg@booker.test")
    res = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-02T18:00:00+00:00",
            "ends_at": "2026-10-02T22:00:00+00:00",
            "buffer_before_min": -15,
            "buffer_after_min": -30,
        },
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 422
