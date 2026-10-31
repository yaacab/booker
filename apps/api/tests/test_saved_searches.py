"""W3-SAVED: saved catalog searches + notify consent gate."""

import pytest

from booker_api.main import app
from booker_api.models import SavedSearch
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


def test_saved_search_list_and_create_reject_foreign_tenant_without_writes(
    client, SessionLocal
):
    ctx = _customer_ctx(client)
    owner = register(client, "saved-foreign-owner@booker.test", "Foreign Owner")
    owner_headers = auth_header(owner["token"])
    other_org = client.post(
        "/orgs", json={"name": "Foreign Search", "kind": "customer"},
        headers=owner_headers,
    ).json()
    other_saved = client.post(
        "/saved-searches",
        json={
            "name": "Private", "organization_id": other_org["id"],
            "query_params": {"city": "Москва"},
        },
        headers=owner_headers,
    )
    assert other_saved.status_code == 201, other_saved.text
    with SessionLocal() as db:
        before = db.query(SavedSearch).count()
    foreign_list = client.get(
        "/saved-searches",
        headers={**ctx["headers"], "X-Booker-Org": other_org["id"]},
    )
    assert foreign_list.status_code == 403
    foreign_create = client.post(
        "/saved-searches",
        json={
            "name": "Forged", "organization_id": other_org["id"],
            "query_params": {"kind": "venue"},
        },
        headers=ctx["headers"],
    )
    assert foreign_create.status_code == 403
    own_list = client.get("/saved-searches", headers=ctx["headers"])
    assert own_list.status_code == 200
    assert other_saved.json()["id"] not in {
        row["id"] for row in own_list.json()["items"]
    }
    with SessionLocal() as db:
        assert db.query(SavedSearch).count() == before
