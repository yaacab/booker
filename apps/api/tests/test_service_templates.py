from tests.conftest import auth_header, register


def test_list_service_templates(client):
    res = client.get("/service-templates")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 3
    assert any(t["id"] == "dj-standard" for t in items)


def test_create_service_from_template(client):
    owner = register(client, "tpl@booker.test", "Tpl")
    org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    res = client.post(
        "/services/from-template",
        json={"organization_id": org["id"], "template_id": "dj-standard", "honorarium_rub": 80000},
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "DJ-сет"
    assert body["category_code"] == "dj"
    assert body["honorarium_rub"] == 80000
