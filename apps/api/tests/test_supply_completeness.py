from tests.conftest import auth_header, register


def test_supply_completeness_for_artist(client):
    owner = register(client, "supply@booker.test", "Supply")
    org = client.post(
        "/orgs",
        json={"name": "Nova", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Nova", "category": "dj"},
        headers=auth_header(owner["token"]),
    )
    res = client.get(
        f"/organizations/{org['id']}/supply-completeness",
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["applicable"] is True
    assert body["score"] < 100
    assert any(item["id"] == "catalog_profile" and item["done"] for item in body["items"])


def test_supply_completeness_customer_not_applicable(client):
    user = register(client, "cust-supply@booker.test", "Cust")
    org = client.post(
        "/orgs",
        json={"name": "Клиент", "kind": "customer"},
        headers=auth_header(user["token"]),
    ).json()
    res = client.get(
        f"/organizations/{org['id']}/supply-completeness",
        headers=auth_header(user["token"]),
    )
    assert res.status_code == 200
    assert res.json()["applicable"] is False


def test_supply_completeness_rejects_foreign_org(client):
    owner = register(client, "supply-private-owner@booker.test")
    outsider = register(client, "supply-private-outsider@booker.test")
    org = client.post(
        "/orgs",
        json={"name": "Private supply", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    denied = client.get(
        f"/organizations/{org['id']}/supply-completeness",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
    assert org["id"] not in denied.text
