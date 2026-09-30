from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from booker_api.models import AuditLog, Event, EventCommandReceipt, Request, TeamMember
from booker_api.security import now
from tests.conftest import auth_header, register


def setup_event(client):
    owner = register(client, "event-command-owner@booker.test")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", headers=headers, json={"name": "Организатор", "kind": "customer"}).json()
    start = now() + timedelta(days=10)
    body = {"organization_id": org["id"], "title": "Ночной корпоратив", "city": "Москва", "event_date": start.isoformat(), "ends_at": (start+timedelta(hours=6)).isoformat(), "event_type": "Корпоратив", "guest_count": 100, "budget_rub": 400000, "requirements": [{"category_code": "dj"}, {"category_code": "photo"}], "idempotency_key": "same-create"}
    return owner, headers, org, body


def test_event_replay_keeps_window_budget_and_single_requirements(client, SessionLocal):
    _, headers, _, body = setup_event(client)
    first = client.post("/events", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/events", headers=headers, json=body).json()
    assert second["id"] == first.json()["id"] and second["reused"]
    assert second["requirements"] == first.json()["requirements"]
    got = client.get(f"/events/{second['id']}", headers=headers).json()
    assert got["budget_rub"] == 400000 and got["event_type"] == "Корпоратив"
    assert datetime.fromisoformat(got["ends_at"]) == datetime.fromisoformat(body["ends_at"])
    assert [r["category_code"] for r in got["requirements"]] == ["dj", "photo"]
    assert client.post("/events", headers=headers, json={**body, "title": "Другая версия"}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Event).count() == db.query(EventCommandReceipt).count() == 1
        assert db.query(AuditLog).filter_by(action="event.created").count() == 1


def test_replay_checks_membership_and_write_role_before_receipt(client, SessionLocal):
    owner, headers, org, body = setup_event(client)
    assert client.post("/events", headers=headers, json=body).status_code == 200
    outsider = register(client, "event-command-outsider@booker.test")
    assert client.post("/events", headers=auth_header(outsider["token"]), json=body).status_code == 403
    with SessionLocal() as db:
        db.query(TeamMember).filter_by(organization_id=org["id"], user_id=owner["user_id"]).one().role = "viewer"; db.commit()
    assert client.post("/events", headers=headers, json=body).status_code == 403


@pytest.mark.parametrize("patch", [{"guest_count": -1}, {"budget_rub": True}, {"title": "  "}, {"event_date": "invalid"}, {"ends_at": "2000-01-01T00:00:00Z"}, {"requirements": [{"category_code": "dj", "qty": 100000}]}])
def test_event_validation_does_not_create_partial_event(client, SessionLocal, patch):
    _, headers, _, body = setup_event(client)
    assert client.post("/events", headers=headers, json={**body, **patch}).status_code == 422
    with SessionLocal() as db:
        assert db.query(Event).count() == 0 and db.query(EventCommandReceipt).count() == 0


def test_request_replay_can_resume_after_second_target_failure(client, SessionLocal):
    _, headers, _, body = setup_event(client)
    event = client.post("/events", headers=headers, json=body).json()
    supplier = register(client, "event-command-supplier@booker.test")
    sh = auth_header(supplier["token"])
    org = client.post("/orgs", headers=sh, json={"name": "Supply", "kind": "artist"}).json()
    artist = client.post("/artists", headers=sh, json={"organization_id": org["id"], "name": "DJ"}).json()
    path = f"/events/{event['id']}/requests"
    data = {"resource_type": "artist", "resource_id": artist["id"], "requirement_id": event["requirements"][0]["id"], "idempotency_key": "target-one"}
    first = client.post(path, json=data, headers=headers)
    assert first.status_code == 200, first.text
    assert client.post(path, json={**data, "resource_id": str(uuid4()), "idempotency_key": "target-two"}, headers=headers).status_code == 404
    replay = client.post(path, json=data, headers=headers)
    assert replay.json()["id"] == first.json()["id"] and replay.json()["reused"]
    assert client.post(path, json={**data, "resource_id": str(uuid4())}, headers=headers).status_code == 409
    assert client.post(path, json=data, headers=sh).status_code == 403
    with SessionLocal() as db:
        assert db.query(Request).count() == 1
        assert db.query(AuditLog).filter_by(action="request.created").count() == 1
        assert db.query(EventCommandReceipt).count() == 2


def test_concurrent_event_retries_use_one_persistent_receipt(client, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from booker_api.db import Base, get_db
    from booker_api.main import app
    engine = create_engine(f"sqlite:///{tmp_path / 'commands.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    old = app.dependency_overrides[get_db]
    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        _, headers, _, body = setup_event(client)
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _: client.post("/events", json=body, headers=headers), range(2)))
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        assert responses[0].json()["id"] == responses[1].json()["id"]
        with sessions() as db:
            assert db.query(Event).count() == 1
    finally:
        app.dependency_overrides[get_db] = old
        engine.dispose()
