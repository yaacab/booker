from datetime import timedelta

from booker_api.security import now
from tests.conftest import auth_header, register


def _supplier(client, email, kind):
    owner = register(client, email, "Поставщик")
    h = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Орг " + kind, "kind": kind}, headers=h).json()
    return h, org


def test_tariff_edit_delete_and_no_invented_price(client):
    h, org = _supplier(client, "wave-artist@booker.test", "artist")
    artist = client.post("/artists", json={"organization_id": org["id"], "name": "Волна", "category": "dj"}, headers=h).json()
    t = client.post(f"/artists/{artist['id']}/tariffs", json={"title": "Сет", "honorarium_rub": 40000, "hours": 2}, headers=h).json()
    upd = client.patch(f"/artists/{artist['id']}/tariffs/{t['id']}", json={"title": "Сет 3 часа", "honorarium_rub": 55000, "hours": 3}, headers=h)
    assert upd.status_code == 200 and upd.json()["honorarium_rub"] == 55000
    assert client.patch(f"/artists/{artist['id']}/tariffs/{t['id']}", json={"honorarium_rub": 0}, headers=h).status_code == 400
    other = register(client, "stranger@booker.test", "Чужой")
    assert client.delete(f"/artists/{artist['id']}/tariffs/{t['id']}", headers=auth_header(other["token"])).status_code in (403, 404)
    assert client.delete(f"/artists/{artist['id']}/tariffs/{t['id']}", headers=h).status_code == 200

    # a customer asks; without a tariff the supplier gets no made-up amount
    ch, corg = _supplier(client, "wave-cust@booker.test", "customer")
    event = client.post("/events", json={"organization_id": corg["id"], "title": "Ужин", "city": "Москва", "guest_count": 60, "budget_rub": 90000,
                                         "notes": "требования:dj,venue\nрайдер:Звук,Свет\nпожелания:без дыма\nзал:Большой",
                                         "event_date": (now() + timedelta(days=15)).isoformat()}, headers=ch).json()
    assert client.post(f"/events/{event['id']}/requests", json={"resource_type": "artist", "resource_id": artist["id"]}, headers=ch).status_code == 200
    items = client.get("/requests", headers=h).json()["items"]
    req = next(i for i in items if i["event_title"] == "Ужин")
    assert req["honorarium_rub"] is None and req["honorarium_source"] == "none"
    assert req["customer_name"] == "Орг customer" and req["guest_count"] == 60 and req["budget_rub"] == 90000 and req["event_city"] == "Москва"
    assert req["brief"] == {"rider": ["Звук", "Свет"], "wishes": "без дыма", "hall": "Большой"}


def test_hall_edit_and_guarded_delete(client):
    h, org = _supplier(client, "wave-venue@booker.test", "venue")
    venue = client.post("/venues", json={"organization_id": org["id"], "name": "Лофт", "capacity": 80}, headers=h).json()
    first = venue["hall_id"]
    assert client.delete(f"/venues/{venue['id']}/halls/{first}", headers=h).status_code == 409  # last hall stays
    second = client.post(f"/venues/{venue['id']}/halls", json={"name": "Малый", "capacity": 20}, headers=h).json()
    upd = client.patch(f"/venues/{venue['id']}/halls/{second['id']}", json={"name": "Камерный", "capacity": 25}, headers=h)
    assert upd.status_code == 200 and upd.json()["name"] == "Камерный" and upd.json()["capacity"] == 25
    assert client.patch(f"/venues/{venue['id']}/halls/{second['id']}", json={"capacity": 0}, headers=h).status_code == 400
    assert client.delete(f"/venues/{venue['id']}/halls/{second['id']}", headers=h).status_code == 200
    t = client.post(f"/venues/{venue['id']}/tariffs", json={"title": "Вечер", "honorarium_rub": 150000}, headers=h).json()
    assert client.patch(f"/venues/{venue['id']}/tariffs/{t['id']}", json={"honorarium_rub": 120000}, headers=h).json()["honorarium_rub"] == 120000
    assert client.delete(f"/venues/{venue['id']}/tariffs/{t['id']}", headers=h).status_code == 200


def test_event_detail_has_budget_brief_and_offer_amounts(client):
    ah, aorg = _supplier(client, "wave-a2@booker.test", "artist")
    artist = client.post("/artists", json={"organization_id": aorg["id"], "name": "Дуэт", "category": "cover"}, headers=ah).json()
    start = now() + timedelta(days=12)
    slot = client.post("/slots", json={"resource_type": "artist", "resource_id": artist["id"], "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=3)).isoformat()}, headers=ah).json()
    ch, corg = _supplier(client, "wave-c2@booker.test", "customer")
    event = client.post("/events", json={"organization_id": corg["id"], "title": "Юбилей", "city": "Москва", "budget_rub": 70000, "notes": "райдер:Звук",
                                         "event_date": start.isoformat()}, headers=ch).json()
    req = client.post(f"/events/{event['id']}/requests", json={"resource_type": "artist", "resource_id": artist["id"]}, headers=ch).json()
    offer = client.post(f"/requests/{req['id']}/offers", json={"honorarium_rub": 35000, "slot_id": slot["id"]}, headers=ah)
    assert offer.status_code == 200, offer.text
    detail = client.get(f"/events/{event['id']}", headers=ch).json()
    assert detail["budget_rub"] == 70000 and detail["brief"]["rider"] == ["Звук"]
    item = detail["requests"][0]
    assert item["offer_honorarium_rub"] == 35000 and item["offer_total_rub"] >= 35000 and item["booking_status"]
    room = client.get(f"/deal-room/{offer.json()['booking_id']}", headers=ch).json()
    assert room["resource_type"] == "artist" and room["resource_name"] == "Дуэт" and room["hall_name"] is None
