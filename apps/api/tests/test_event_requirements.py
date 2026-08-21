from tests.conftest import auth_header, register


def test_put_requirements_and_viewer_forbidden(client):
    owner = register(client, "req-own@booker.test", "Own")
    viewer = register(client, "req-view@booker.test", "View")
    h = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Клиент", "kind": "customer"}, headers=h).json()
    add = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=h,
    )
    assert add.status_code == 200

    created = client.post(
        "/events",
        json={
            "organization_id": org["id"],
            "title": "Свадьба",
            "event_date": "2026-09-01T18:00:00+00:00",
        },
        headers=h,
    )
    assert created.status_code == 200, created.text
    event_id = created.json()["id"]

    replaced = client.put(
        f"/events/{event_id}/requirements",
        json={
            "items": [
                {"category_code": "host", "qty": 1, "notes": "ведущий"},
                {"category_code": "photo", "qty": 2},
            ]
        },
        headers=h,
    )
    assert replaced.status_code == 200, replaced.text
    codes = [r["category_code"] for r in replaced.json()["requirements"]]
    assert codes == ["host", "photo"]

    got = client.get(f"/events/{event_id}", headers=h)
    assert got.status_code == 200
    shown = got.json()["requirements"]
    assert [r["category_code"] for r in shown] == ["host", "photo"]
    assert shown[0]["qty"] == 1
    assert shown[0]["notes"] == "ведущий"
    assert shown[1]["qty"] == 2

    denied = client.put(
        f"/events/{event_id}/requirements",
        json={"items": [{"category_code": "dj", "qty": 1}]},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
