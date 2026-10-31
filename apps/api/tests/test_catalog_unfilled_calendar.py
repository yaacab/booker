from datetime import timedelta

from booker_api.models import Artist, AvailabilitySlot
from booker_api.security import now
from tests.conftest import auth_header, register


def _artist(client, SessionLocal, email, name, city="Москва", verified=True):
    owner = register(client, email, name)
    org = client.post("/orgs", json={"name": name, "kind": "artist"}, headers=auth_header(owner["token"])).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": name, "category": "cover", "city": city},
        headers=auth_header(owner["token"]),
    ).json()
    with SessionLocal() as db:
        row = db.get(Artist, artist["id"])
        row.verified = verified
        row.verified_status = "approved" if verified else "pending"
        row.city = city
        db.commit()
    return owner, artist


def _slot(SessionLocal, artist_id, start, hours=3, status="open"):
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type="artist", resource_id=artist_id, starts_at=start, ends_at=start + timedelta(hours=hours),
                                status=status, buffer_before_min=0, buffer_after_min=0))
        db.commit()


def test_published_artist_without_calendar_is_listed_after_open_ones(client, SessionLocal):
    _, open_artist = _artist(client, SessionLocal, "open@booker.test", "Открытый")
    _, empty_artist = _artist(client, SessionLocal, "empty@booker.test", "Без календаря")
    _, past_artist = _artist(client, SessionLocal, "past@booker.test", "Прошлые слоты")
    _, hidden = _artist(client, SessionLocal, "pending@booker.test", "Не опубликован", verified=False)
    _slot(SessionLocal, open_artist["id"], now() + timedelta(days=3))
    _slot(SessionLocal, past_artist["id"], now() - timedelta(days=10))

    items = client.get("/catalog/search", params={"city": "Москва", "category": "cover"}).json()["items"]
    ids = [i["id"] for i in items]
    assert ids[0] == open_artist["id"]
    assert set(ids[1:]) == {empty_artist["id"], past_artist["id"]}
    assert hidden["id"] not in ids
    by_id = {i["id"]: i for i in items}
    assert by_id[open_artist["id"]]["calendar_status"] == "open" and by_id[open_artist["id"]]["has_calendar"] is True
    for aid in (empty_artist["id"], past_artist["id"]):
        assert by_id[aid]["calendar_status"] == "unfilled"
        assert by_id[aid]["has_calendar"] is False
        assert by_id[aid]["open_slots"] == 0 and by_id[aid]["next_open_at"] is None


def test_busy_on_requested_date_stays_hidden_but_unfilled_is_listed(client, SessionLocal):
    _, busy = _artist(client, SessionLocal, "busy@booker.test", "Занят")
    _, empty_artist = _artist(client, SessionLocal, "empty2@booker.test", "Пустой")
    day = (now() + timedelta(days=5)).replace(hour=15, minute=0, second=0, microsecond=0)
    _slot(SessionLocal, busy["id"], day, status="busy")
    _slot(SessionLocal, busy["id"], day + timedelta(days=1))  # has a future calendar, free only on another day

    items = client.get("/catalog/search", params={"city": "Москва", "category": "cover", "date": day.isoformat()}).json()["items"]
    ids = [i["id"] for i in items]
    assert busy["id"] not in ids
    assert empty_artist["id"] in ids


def test_empty_city_means_all_cities(client, SessionLocal):
    _, msk = _artist(client, SessionLocal, "msk@booker.test", "Москвич")
    _, spb = _artist(client, SessionLocal, "spb@booker.test", "Питерец", city="Санкт-Петербург")
    all_ids = {i["id"] for i in client.get("/catalog/search", params={"category": "cover"}).json()["items"]}
    assert {msk["id"], spb["id"]} <= all_ids
    blank = {i["id"] for i in client.get("/catalog/search", params={"category": "cover", "city": ""}).json()["items"]}
    assert {msk["id"], spb["id"]} <= blank
    spb_only = {i["id"] for i in client.get("/catalog/search", params={"category": "cover", "city": "Санкт-Петербург"}).json()["items"]}
    assert spb_only == {spb["id"]}


def test_seed_profile_without_account_is_not_public(client, SessionLocal):
    from booker_api.models import Organization
    _, real = _artist(client, SessionLocal, "real@booker.test", "Настоящий")
    with SessionLocal() as db:  # what seed.py does: an organization with no members, a "verified" artist
        org = Organization(name="Сид", kind="artist", city="Москва")
        db.add(org); db.flush()
        seed = Artist(organization_id=org.id, name="Сид Профиль", city="Москва", category="cover", verified=True, verified_status="approved")
        db.add(seed); db.commit(); seed_id = seed.id
    ids = {i["id"] for i in client.get("/catalog/search", params={"category": "cover"}).json()["items"]}
    assert real["id"] in ids
    assert seed_id not in ids
    assert client.get(f"/artists/{seed_id}").status_code == 404
    assert client.get(f"/artists/{real['id']}").status_code == 200


def test_requests_to_seed_artist_are_rejected(client, SessionLocal):
    from booker_api.models import Organization
    with SessionLocal() as db:
        org = Organization(name="Сид2", kind="artist", city="Москва"); db.add(org); db.flush()
        seed = Artist(organization_id=org.id, name="Сид Два", city="Москва", category="cover", verified=True, verified_status="approved")
        db.add(seed); db.commit(); seed_id = seed.id
    customer = register(client, "cust-seed@booker.test", "Заказчик")
    h = auth_header(customer["token"])
    org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=h).json()
    event = client.post("/events", json={"organization_id": org["id"], "title": "Тест", "city": "Москва", "event_date": (now() + timedelta(days=20)).isoformat()}, headers=h)
    assert event.status_code == 200, event.text
    res = client.post(f"/events/{event.json()['id']}/requests", json={"resource_type": "artist", "resource_id": seed_id}, headers=h)
    assert res.status_code == 404
    quick = client.post("/quick-request", json={"artist_id": seed_id, "slot_id": "x"}, headers=h)
    assert quick.status_code == 404


def test_qa_cabinets_are_bookable_but_not_listed(client, SessionLocal):
    _, qa_artist = _artist(client, SessionLocal, "qa-artist@qa.bukergo.ru", "QA Артист")
    _, real = _artist(client, SessionLocal, "real2@booker.test", "Живой")
    ids = {i["id"] for i in client.get("/catalog/search", params={"category": "cover"}).json()["items"]}
    assert real["id"] in ids and qa_artist["id"] not in ids
    assert client.get(f"/artists/{qa_artist['id']}").status_code == 200
    customer = register(client, "qa-customer@qa.bukergo.ru", "QA Заказчик")
    h = auth_header(customer["token"])
    org = client.post("/orgs", json={"name": "QA", "kind": "customer"}, headers=h).json()
    event = client.post("/events", json={"organization_id": org["id"], "title": "QA", "city": "Москва", "event_date": (now() + timedelta(days=20)).isoformat()}, headers=h).json()
    res = client.post(f"/events/{event['id']}/requests", json={"resource_type": "artist", "resource_id": qa_artist["id"]}, headers=h)
    assert res.status_code == 200, res.text
