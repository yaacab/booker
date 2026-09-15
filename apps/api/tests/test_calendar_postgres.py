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


def coordinated_race(monkeypatch, module, pause_name, run, *, expected_second=409):
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
        assert second.result(timeout=5) == expected_second


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


@pytest.mark.parametrize('first_action,second_action', [('hold', 'version'), ('version', 'hold'), ('version', 'ack')])
def test_postgres_quote_change_and_hold_use_same_event_lock(client, SessionLocal, monkeypatch, first_action, second_action):
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx)
    acknowledged(client, ctx, offer)
    first_ready, second_at_lock, release = Signal(), Signal(), Signal()
    thread = local()
    original_lock = deals._lock_open_event
    pause_name = '_apply_hold' if first_action == 'hold' else 'offer_fees'
    original_pause = getattr(deals, pause_name)

    def pause(*args, **kwargs):
        if thread.role == 'first':
            first_ready.set()
            assert release.wait(5)
        return original_pause(*args, **kwargs)

    def lock(*args, **kwargs):
        if thread.role == 'second':
            second_at_lock.set()
        return original_lock(*args, **kwargs)

    def run(role, action):
        thread.role = role
        with SessionLocal() as db:
            user = db.get(User, ctx['owner']['user_id'])
            try:
                if action == 'hold':
                    deals.hold_booking(offer['booking_id'], user=user, db=db)
                elif action == 'version':
                    deals.new_version(offer['id'], {'honorarium_rub': 125000}, user=user, db=db)
                else:
                    deals.ack_offer(offer['id'], {'side': 'customer', 'quote_id': offer['version']['id']}, user=user, db=db)
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code

    monkeypatch.setattr(deals, '_lock_open_event', lock)
    monkeypatch.setattr(deals, pause_name, pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, 'first', first_action)
        try:
            assert first_ready.wait(5)
            second = pool.submit(run, 'second', second_action)
            assert second_at_lock.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.2)
        finally:
            release.set()
        assert first.result(timeout=5) == 200
        assert second.result(timeout=5) == 409
    from booker_api.models import Booking, Offer, OfferVersion
    with SessionLocal() as db:
        booking = db.get(Booking, offer['booking_id'])
        active = db.get(OfferVersion, db.get(Offer, offer['id']).active_version_id)
        if first_action == 'hold':
            assert booking.status == 'DateHeld'
            assert active.id == offer['version']['id']
        else:
            assert booking.status == 'Negotiation'
            assert active.honorarium_rub == 125000
            assert not active.customer_ack and not active.supplier_ack


def test_postgres_cancel_alternative_waits_for_other_hold_and_preserves_it(client, SessionLocal, monkeypatch):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx)
    acknowledged(client, ctx, first)
    from booker_api.models import Booking
    with SessionLocal() as db:
        slot_id = db.get(Booking, first['booking_id']).slot_id
    event = client.post('/events', headers=ctx['headers'], json={'organization_id': ctx['customer']['id'], 'title': 'Другое событие', 'event_date': ctx['start'].isoformat(), 'ends_at': ctx['end'].isoformat()}).json()
    req = client.post(f"/events/{event['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': ctx['artists'][0]['id']}).json()
    response = client.post(f"/requests/{req['id']}/offers", headers=ctx['headers'], json={'slot_id': slot_id, 'honorarium_rub': 70000})
    assert response.status_code == 200, response.text
    second = response.json()

    def run(role):
        with SessionLocal() as db:
            user = db.get(User, ctx['owner']['user_id'])
            try:
                if role == 'first':
                    deals.hold_booking(first['booking_id'], user=user, db=db)
                else:
                    deals.cancel_booking(second['booking_id'], user=user, db=db)
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code

    coordinated_race(monkeypatch, deals, '_apply_hold', run, expected_second=200)
    with SessionLocal() as db:
        assert db.get(Booking, first['booking_id']).status == 'DateHeld'
        assert db.get(Booking, second['booking_id']).status == 'Cancelled'
        assert db.get(AvailabilitySlot, slot_id).status == 'held'
        assert db.query(BookingHold).filter_by(status='active').count() == 1


def test_postgres_both_contract_signatures_commit_once(client, SessionLocal, monkeypatch):
    from booker_api.models import AuditLog, Booking, Contract, InboxNotification, Message
    from booker_api.routers import payments
    from tests.conftest import contract_otps
    from tests.test_contract_guards import prepared
    ctx, offer = prepared(client, SessionLocal)
    contract = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).json()
    codes = contract_otps(SessionLocal, contract['id'])
    first_ready, second_at_lock, release = Signal(), Signal(), Signal()
    thread = local()
    original_lock = payments._lock_contract_event
    original_validate = payments._require_contract_reservation

    def lock(*args, **kwargs):
        if thread.side == 'supplier':
            second_at_lock.set()
        return original_lock(*args, **kwargs)

    def validate(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        if thread.side == 'customer':
            first_ready.set()
            assert release.wait(5)
        return result

    def run(side):
        thread.side = side
        with SessionLocal() as db:
            return payments.sign_contract(contract['id'], payments.SignIn(side=side, otp=codes[f'otp_{side}']), user=db.get(User, ctx['owner']['user_id']), db=db)

    monkeypatch.setattr(payments, '_lock_contract_event', lock)
    monkeypatch.setattr(payments, '_require_contract_reservation', validate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, 'customer')
        try:
            assert first_ready.wait(5)
            second = pool.submit(run, 'supplier')
            assert second_at_lock.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.2)
        finally:
            release.set()
        assert first.result(timeout=5)['customer_signed']
        assert second.result(timeout=5)['booking_status'] == 'AwaitingPayment'
    for side in ['customer', 'supplier']:
        assert run(side)['booking_status'] == 'AwaitingPayment'
    with SessionLocal() as db:
        signed = db.get(Contract, contract['id'])
        assert signed.customer_signed and signed.supplier_signed
        assert db.get(Booking, offer['booking_id']).status == 'AwaitingPayment'
        assert db.query(AuditLog).filter_by(action='contract.signed', entity_id=contract['id']).count() == 2
        assert db.query(InboxNotification).filter_by(template='payment.required').count() == 1
        assert db.query(Message).filter_by(body='Договор подписан. Ожидается предоплата.').count() == 1


def test_postgres_commercial_report_cohorts_and_source_groups(client, SessionLocal):
    from tests.test_commercial_revenue import (
        test_revenue_separates_money_quotes_tests_and_unknown_fees,
    )
    test_revenue_separates_money_quotes_tests_and_unknown_fees(client, SessionLocal)


@pytest.mark.parametrize('first_action,second_action', [('capture', 'cancel'), ('cancel', 'capture'), ('capture', 'expiry'), ('expiry', 'capture')])
def test_postgres_capture_cancel_expiry_share_reservation_lock(client, SessionLocal, monkeypatch, first_action, second_action):
    from datetime import timedelta

    from booker_api.models import Booking, Payment
    from booker_api.routers import payments
    from tests.test_payments import _awaiting_payment, _sign
    ctx = _awaiting_payment(client)
    ready, second_at_lock, release = Signal(), Signal(), Signal()
    thread = local()
    real_now = deals.now
    from booker_api.security import aware
    with SessionLocal() as db:
        expiry_moment = aware(db.query(BookingHold).filter_by(booking_id=ctx["booking_id"], status="active").one().expires_at)+timedelta(seconds=1)
    def logical_now():
        return expiry_moment if first_action == 'expiry' or getattr(thread, 'action', '') == 'expiry' else real_now()
    monkeypatch.setattr(deals, 'now', logical_now)
    monkeypatch.setattr(payments, 'now', logical_now)
    original_deal_lock, original_payment_lock = deals._lock_event, payments._lock_contract_event
    def lock(original, *args, **kwargs):
        if getattr(thread, 'role', '') == 'second':
            second_at_lock.set()
        return original(*args, **kwargs)
    monkeypatch.setattr(deals, '_lock_event', lambda *a, **kw: lock(original_deal_lock, *a, **kw))
    monkeypatch.setattr(payments, '_lock_contract_event', lambda *a, **kw: lock(original_payment_lock, *a, **kw))
    def pause():
        if thread.role == 'first':
            ready.set()
            assert release.wait(10)
    original_confirm, original_transition, original_audit = payments._confirm_captured_booking, deals._transition, deals.audit
    def confirm(*a, **kw):
        result = original_confirm(*a, **kw)
        if first_action == 'capture':
            pause()
        return result
    def transition(booking, target):
        result = original_transition(booking, target)
        if first_action == 'cancel' and target == 'Cancelled':
            pause()
        return result
    def audit(*a, **kw):
        if first_action == 'expiry' and kw.get('action') == 'hold.expired':
            pause()
        return original_audit(*a, **kw)
    monkeypatch.setattr(payments, '_confirm_captured_booking', confirm)
    monkeypatch.setattr(deals, '_transition', transition)
    monkeypatch.setattr(deals, 'audit', audit)
    def run(role, action):
        thread.role, thread.action = role, action
        with SessionLocal() as db:
            if action == 'capture':
                if role == 'first':
                    return payments._apply_payment_webhook(payments.WebhookIn(event_id='capture-race', payment_id=ctx['payment_id'], status='succeeded', signature=_sign('capture-race', ctx['payment_id'], 'succeeded')), db)
                return payments.capture_payment_as_succeeded(db, payment=db.get(Payment, ctx['payment_id']), actor_user_id=None, event_id='capture-race', note='test capture')
            if action == 'cancel':
                return deals.cancel_booking(ctx['booking_id'], user=db.get(User, ctx['customer']['user_id']), db=db)
            result = deals.expire_holds(db); db.commit(); return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, 'first', first_action)
        try:
            assert ready.wait(10)
            second = pool.submit(run, 'second', second_action)
            assert second_at_lock.wait(10)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.2)
        finally:
            release.set()
        first.result(timeout=10); second.result(timeout=10)
    with SessionLocal() as db:
        booking = db.get(Booking, ctx['booking_id'])
        slot = db.get(AvailabilitySlot, booking.slot_id)
        assert db.get(Payment, ctx['payment_id']).status == 'succeeded'
        if 'cancel' in {first_action, second_action}:
            assert booking.status == 'Cancelled' and slot.status == 'open'
        elif first_action == 'capture':
            assert booking.status == 'Confirmed' and slot.status == 'confirmed'
            assert db.query(BookingHold).filter_by(booking_id=booking.id, status='active').count() == 0
        else:
            assert booking.status == 'AwaitingPayment' and slot.status == 'open'
