from booker_api.config import Settings, settings
from booker_api.models import User
from tests.conftest import auth_header, grant_team_plan, register


def _registration_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "password1",
        "full_name": "Участник пилота",
        "phone": "+79000000000",
        "accept_offer": True,
        "accept_privacy": True,
        "marketing_opt_in": False,
    }


def test_public_registration_defaults_to_closed(monkeypatch):
    monkeypatch.delenv("BOOKER_PUBLIC_REGISTRATION_ENABLED", raising=False)
    configured = Settings(_env_file=None, environment="production")
    assert configured.environment == "production"
    assert configured.public_registration_enabled is False


def test_closed_registration_rejects_direct_api_but_keeps_login(
    client,
    SessionLocal,
    monkeypatch,
):
    existing = register(client, "invited@booker.test", "Приглашённый участник")
    monkeypatch.setattr(settings, "public_registration_enabled", False)

    denied = client.post(
        "/auth/register",
        json=_registration_payload("public-signup@booker.test"),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"].startswith("Саморегистрация временно закрыта")

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "public-signup@booker.test").one_or_none() is None
    finally:
        db.close()

    login = client.post(
        "/auth/login",
        json={"email": "invited@booker.test", "password": "password1"},
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == existing["user_id"]


def test_register_requires_legal_accept(client):
    denied = client.post(
        "/auth/register",
        json={"email": "nolegal@booker.test", "password": "password1", "full_name": "X"},
    )
    assert denied.status_code == 422
    ok = client.post(
        "/auth/register",
        json={
            "email": "legalok@booker.test",
            "password": "password1",
            "full_name": "X",
            "accept_offer": True,
            "accept_privacy": True,
            "marketing_opt_in": False,
        },
    )
    assert ok.status_code == 200


def test_recover_does_not_reveal_email(client):
    missing = client.post("/auth/recover", json={"email": "nobody@booker.test"})
    exists = client.post("/auth/recover", json={"email": "a@booker.test"})
    assert missing.status_code == 200
    assert exists.status_code == 200
    assert missing.json()["ok"] is True
    assert exists.json()["ok"] is True


def test_cannot_read_foreign_org(client):
    a = register(client, "a@booker.test", "A")
    b = register(client, "b@booker.test", "B")
    org = client.post(
        "/orgs",
        json={"name": "A Org", "kind": "customer"},
        headers=auth_header(a["token"]),
    )
    assert org.status_code == 200
    foreign = client.get(f"/orgs/{org.json()['id']}", headers=auth_header(b["token"]))
    assert foreign.status_code == 403


def test_member_without_confirm_cannot_ack_offer(client):
    customer = register(client, "cust@booker.test", "Cust")
    owner = register(client, "owner@booker.test", "Owner")
    manager = register(client, "mgr@booker.test", "Mgr")

    cust_org = client.post(
        "/orgs",
        json={"name": "Клиент", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Артисты", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    grant_team_plan(client, artist_org['id'])
    add = client.post(
        f"/orgs/{artist_org['id']}/members",
        json={"user_id": manager["user_id"], "role": "manager", "can_confirm_offer": False},
        headers=auth_header(owner["token"]),
    )
    assert add.status_code == 200

    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-09-01T18:00:00+00:00",
            "ends_at": "2026-09-01T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Свадьба",
            "event_date": "2026-09-01T18:00:00+00:00",
        },
        headers=auth_header(customer["token"]),
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=auth_header(customer["token"]),
    ).json()
    denied = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"]},
        headers=auth_header(manager["token"]),
    )
    assert denied.status_code == 403
