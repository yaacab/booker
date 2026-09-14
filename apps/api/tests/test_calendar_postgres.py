"""Real PostgreSQL concurrency checks; BOOKER_TEST_POSTGRES_URL selects a disposable test server."""
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event as Signal
from threading import local
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from booker_api.db import Base
from booker_api.models import AvailabilitySlot, BookingHold, User
from booker_api.routers import catalog, deals
from booker_api.schemas import SlotIn
from tests.test_event_budget import offer_for
from tests.test_hold_authorization import acknowledged
from tests.test_matching import setup_matching


@pytest.fixture()
def engine():
    url = os.getenv('BOOKER_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('BOOKER_TEST_POSTGRES_URL is required for PostgreSQL concurrency tests')
    schema = 'booker_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    eng = create_engine(url, connect_args={'options': f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000'})
    try:
        Base.metadata.create_all(eng)
        yield eng
    finally:
        eng.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def coordinated_race(monkeypatch, module, pause_name, run):
    """Pause writer one after validation, prove writer two waits on the parent lock."""
    first_ready, second_at_lock, release = Signal(), Signal(), Signal()
    thread = local()
    original_pause = getattr(module, pause_name)
    original_lock = module.lock_calendar_resources

    def pause(*args, **kwargs):
        result = original_pause(*args, **kwargs) if pause_name == 'overlapping_slots' else None
        if thread.role == 'first':
            first_ready.set()
            assert release.wait(5), 'Second writer did not reach the lock'
        return result if pause_name == 'overlapping_slots' else original_pause(*args, **kwargs)

    def lock(*args, **kwargs):
        if thread.role == 'second':
            second_at_lock.set()
        return original_lock(*args, **kwargs)

    def execute(role):
        thread.role = role
        return run(role)

    monkeypatch.setattr(module, pause_name, pause)
    monkeypatch.setattr(module, 'lock_calendar_resources', lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute, 'first')
        try:
            assert first_ready.wait(5)
            second = pool.submit(execute, 'second')
            assert second_at_lock.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.2)
        finally:
            release.set()
        assert first.result(timeout=5) == 200
        assert second.result(timeout=5) == 409


def test_postgres_concurrent_slot_creation_serializes_empty_calendar(client, SessionLocal, monkeypatch):
    ctx = setup_matching(client)
    resource = ctx['artists'][0]['id']
    with SessionLocal() as db:
        db.query(AvailabilitySlot).filter_by(resource_id=resource).delete(); db.commit()
    body = SlotIn(resource_type='artist', resource_id=resource, starts_at=ctx['start'], ends_at=ctx['end'])

    def run(role):
        with SessionLocal() as db:
            try:
                catalog.create_slot(body, user=db.get(User, ctx['owner']['user_id']), db=db)
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code

    coordinated_race(monkeypatch, catalog, 'overlapping_slots', run)
    with SessionLocal() as db:
        assert db.query(AvailabilitySlot).filter_by(resource_id=resource).count() == 1


def test_postgres_holds_on_distinct_overlapping_slots_have_one_winner(client, SessionLocal, monkeypatch):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx)
    resource = ctx['artists'][0]['id']
    with SessionLocal() as db:
        old = db.query(AvailabilitySlot).filter_by(resource_id=resource).one()
        slot = AvailabilitySlot(resource_type='artist', resource_id=resource, starts_at=old.starts_at, ends_at=old.ends_at, status='open')
        db.add(slot); db.commit(); slot_id = slot.id
    response = client.post('/events', headers=ctx['headers'], json={'organization_id': ctx['customer']['id'], 'title': 'Другой заказчик того же интервала', 'event_date': ctx['start'].isoformat(), 'ends_at': ctx['end'].isoformat()})
    event_id = response.json()['id']
    req = client.post(f'/events/{event_id}/requests', headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': resource}).json()
    response = client.post(f"/requests/{req['id']}/offers", headers=ctx['headers'], json={'slot_id': slot_id, 'honorarium_rub': 70000})
    assert response.status_code == 200, response.text
    second = response.json()
    for offer in [first, second]:
        acknowledged(client, ctx, offer)

    def run(role):
        with SessionLocal() as db:
            try:
                booking_id = (first if role == 'first' else second)['booking_id']
                deals.hold_booking(booking_id, user=db.get(User, ctx['owner']['user_id']), db=db)
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code

    coordinated_race(monkeypatch, deals, '_apply_hold', run)
    with SessionLocal() as db:
        assert db.query(BookingHold).filter_by(status='active').count() == 1
        assert db.get(AvailabilitySlot, slot_id).status == 'open'
