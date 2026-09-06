"""W3-SAVED: saved catalog searches + notify consent gate."""

import pytest

from booker_api.main import app
from booker_api.routers import saved_searches as saved_searches_router
from tests.conftest import auth_header, register


@pytest.fixture(scope="module", autouse=True)
def _mount_saved_searches_router():
    if not any(getattr(r, "path", None) == "/saved-searches" for r in app.routes):
        app.include_router(saved_searches_router.router)
    yield


def _customer_ctx(client):
    user = register(client, "saved-cust@booker.test", "Заказчик SAVE")
    headers = auth_header(user["token"])
    org = client.post(
        "/orgs",
        json={"name": "Клиент SAVED", "kind": "customer"},
        headers=headers,
    ).json()
    headers["X-Booker-Org"] = org["id"]
    return {"headers": headers, "org": org}


def test_create_list_delete_saved_search(client):
    ctx = _customer_ctx(client)
    created = client.post(
        "/saved-searches",
        json={
            "name": "DJ на пятницу",
            "organization_id": ctx["org"]["id"],
            "query_params": {
                "city": "Москва",
                "format": "dj",
                "budget_max": 150000,
                "guests": 80,
                "kind": "artist",
            },
        },
        headers=ctx["headers"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "DJ на пятницу"
    assert body["query_params"]["city"] == "Москва"
    assert body["notify_consent"] is False
    assert body["search_path"].startswith("/search?")

    listed = client.get("/saved-searches", headers=ctx["headers"])
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]

    deleted = client.delete(f"/saved-searches/{body['id']}", headers=ctx["headers"])
    assert deleted.status_code == 204, deleted.text

    empty = client.get("/saved-searches", headers=ctx["headers"])
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_notify_consent_requires_explicit_consent_on_create(client):
    ctx = _customer_ctx(client)
    denied = client.post(
        "/saved-searches",
        json={
            "name": "Спам",
            "organization_id": ctx["org"]["id"],
            "query_params": {"city": "Москва"},
            "notify_consent": True,
        },
        headers=ctx["headers"],
    )
    assert denied.status_code == 400
    assert "согласие" in denied.json()["detail"].lower()

    allowed = client.post(
        "/saved-searches",
        json={
            "name": "С согласием",
            "organization_id": ctx["org"]["id"],
            "query_params": {"city": "Москва"},
            "notify_consent": True,
            "consent": True,
        },
        headers=ctx["headers"],
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["notify_consent"] is True


def test_patch_notify_consent_gate(client):
    ctx = _customer_ctx(client)
    created = client.post(
        "/saved-searches",
        json={
            "name": "Без уведомлений",
            "organization_id": ctx["org"]["id"],
            "query_params": {"kind": "venue", "guests": 50},
        },
        headers=ctx["headers"],
    ).json()

    denied = client.patch(
        f"/saved-searches/{created['id']}/notify-consent",
        json={"notify_consent": True},
        headers=ctx["headers"],
    )
    assert denied.status_code == 400

    enabled = client.patch(
        f"/saved-searches/{created['id']}/notify-consent",
        json={"notify_consent": True, "consent": True},
        headers=ctx["headers"],
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["notify_consent"] is True

    disabled = client.patch(
        f"/saved-searches/{created['id']}/notify-consent",
        json={"notify_consent": False},
        headers=ctx["headers"],
    )
    assert disabled.status_code == 200
    assert disabled.json()["notify_consent"] is False


def test_stranger_cannot_delete(client):
    ctx = _customer_ctx(client)
    created = client.post(
        "/saved-searches",
        json={
            "name": "Чужой",
            "organization_id": ctx["org"]["id"],
            "query_params": {"city": "Москва"},
        },
        headers=ctx["headers"],
    ).json()
    stranger = auth_header(register(client, "saved-other@booker.test", "Другой")["token"])
    denied = client.delete(f"/saved-searches/{created['id']}", headers=stranger)
    assert denied.status_code == 404
