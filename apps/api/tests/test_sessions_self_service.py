from booker_api.models import SessionToken, UserNotification
from tests.conftest import auth_header, register


def test_list_sessions_marks_current(client):
    user = register(client, "sess-list@booker.test", "Сессии")
    listed = client.get("/me/sessions", headers=auth_header(user["token"]))
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["current"] is True
    assert items[0]["id"]


def test_revoke_others_keeps_current_session(client, SessionLocal):
    user = register(client, "sess-revoke@booker.test", "Сессии2")
    first = auth_header(user["token"])
    second_login = client.post(
        "/auth/login",
        json={"email": "sess-revoke@booker.test", "password": "password1"},
    )
    assert second_login.status_code == 200, second_login.text
    second_token = second_login.json()["token"]
    second = auth_header(second_token)

    before = client.get("/me/sessions", headers=first)
    assert before.status_code == 200
    assert len(before.json()["items"]) == 2

    revoked = client.post("/me/sessions/revoke-others", headers=first)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] == 1

    still = client.get("/me/sessions", headers=first)
    assert still.status_code == 200
    items = still.json()["items"]
    assert len(items) == 1
    assert items[0]["current"] is True

    dead = client.get("/me", headers=second)
    assert dead.status_code == 401

    with SessionLocal() as db:
        assert db.query(SessionToken).filter_by(user_id=user["user_id"]).count() == 1
        notices = (
            db.query(UserNotification)
            .filter_by(recipient_user_id=user["user_id"], template="security.sessions_revoked")
            .count()
        )
        assert notices >= 1


def test_cannot_delete_current_session_via_id(client):
    user = register(client, "sess-current@booker.test", "Сессии3")
    headers = auth_header(user["token"])
    listed = client.get("/me/sessions", headers=headers).json()["items"]
    current_id = listed[0]["id"]
    denied = client.delete(f"/me/sessions/{current_id}", headers=headers)
    assert denied.status_code == 409


def test_delete_other_session_by_id(client):
    user = register(client, "sess-one@booker.test", "Сессии4")
    first = auth_header(user["token"])
    second_login = client.post(
        "/auth/login",
        json={"email": "sess-one@booker.test", "password": "password1"},
    )
    assert second_login.status_code == 200
    second = auth_header(second_login.json()["token"])
    other_id = next(
        item["id"]
        for item in client.get("/me/sessions", headers=first).json()["items"]
        if not item["current"]
    )
    deleted = client.delete(f"/me/sessions/{other_id}", headers=first)
    assert deleted.status_code == 200, deleted.text
    assert client.get("/me", headers=second).status_code == 401
    assert len(client.get("/me/sessions", headers=first).json()["items"]) == 1


def test_identities_include_provider_config_flags(client):
    user = register(client, "prov-flags@booker.test", "Провайдеры")
    res = client.get("/me/identities", headers=auth_header(user["token"]))
    assert res.status_code == 200, res.text
    providers = res.json()["providers"]
    assert providers["telegram"]["configured"] is False
    assert providers["yandex"]["configured"] is False
    assert providers["vk"]["configured"] is False
