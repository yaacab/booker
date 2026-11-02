"""ART-06: supply-initiated artist verification request → admin queue."""

from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET


def _owner_with_artist(client, suffix: str):
    owner = register(client, f"art06-owner-{suffix}@booker.test", "Артист")
    org = client.post(
        "/orgs",
        json={"name": f"Шоу ART06 {suffix}", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": f"DJ ART06 {suffix}", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, org, artist


def test_supply_can_request_verification_and_admin_sees_queue(client):
    owner, _org, artist = _owner_with_artist(client, "main")
    headers = auth_header(owner["token"])

    requested = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={"notes": "готовы к проверке"},
        headers=headers,
    )
    assert requested.status_code == 200, requested.text
    body = requested.json()
    assert body["status"] == "queued"
    assert body["idempotent"] is False

    again = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={},
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["idempotent"] is True
    assert again.json()["id"] == body["id"]

    private = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert private["verification_request_queued"] is True
    assert private["can_request_verification"] is False
    assert private["verified_status"] == "pending"

    admin = _promote_admin(client, "art06-admin@booker.test", totp=TEST_TOTP_SECRET)
    queue = client.get("/admin/verifications", headers=auth_header(admin["token"]))
    assert queue.status_code == 200, queue.text
    payload = queue.json()
    assert any(row["id"] == body["id"] for row in payload["queue"])
    assert any(row["id"] == artist["id"] for row in payload["artists"])

    decided = client.post(
        "/admin/verifications",
        json={"target_type": "artist", "target_id": artist["id"], "approve": True, "notes": "ok"},
        headers=auth_header(admin["token"]),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["verified"] is True

    after = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert after["verified"] is True
    assert after["verified_status"] == "approved"
    assert after["can_request_verification"] is False
    assert after["verification_request_queued"] is False

    blocked = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={},
        headers=headers,
    )
    assert blocked.status_code == 409


def test_verification_request_authz(client):
    owner, org, artist = _owner_with_artist(client, "authz")
    outsider = register(client, "art06-out@booker.test", "Чужой")
    denied = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={},
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403

    viewer = register(client, "art06-viewer@booker.test", "Зритель")
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(owner["token"]),
    )
    assert added.status_code == 200, added.text
    viewer_denied = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={},
        headers=auth_header(viewer["token"]),
    )
    assert viewer_denied.status_code == 403


def test_rejected_artist_can_request_again(client):
    owner, _org, artist = _owner_with_artist(client, "reject")
    headers = auth_header(owner["token"])
    admin = _promote_admin(client, "art06-admin2@booker.test", totp=TEST_TOTP_SECRET)

    first = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={},
        headers=headers,
    )
    assert first.status_code == 200
    reject = client.post(
        "/admin/verifications",
        json={
            "target_type": "artist",
            "target_id": artist["id"],
            "approve": False,
            "notes": "мало материалов",
        },
        headers=auth_header(admin["token"]),
    )
    assert reject.status_code == 200
    profile = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert profile["verified"] is False
    assert profile["verified_status"] == "rejected"
    assert profile["can_request_verification"] is True

    second = client.post(
        f"/artists/{artist['id']}/verification-request",
        json={"notes": "добавили портфолио"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["idempotent"] is False
    assert second.json()["status"] == "queued"
