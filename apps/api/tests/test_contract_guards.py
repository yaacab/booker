from datetime import timedelta

import pytest

from booker_api.models import (
    AuditLog,
    Booking,
    BookingHold,
    Contract,
    Event,
    InboxNotification,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, contract_otps, register
from tests.test_event_budget import offer_for
from tests.test_event_readiness import hold
from tests.test_matching import setup_matching


def prepared(client, SessionLocal):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    hold(client, ctx, offer)
    return ctx, offer


def test_viewer_cannot_create_or_sign_and_does_not_receive_codes(client, SessionLocal):
    ctx, offer = prepared(client, SessionLocal)
    viewer = register(client, 'contract-viewer@booker.test')
    with SessionLocal() as db:
        for org in [ctx['customer']['id'], ctx['supply']['id']]:
            db.add(TeamMember(user_id=viewer['user_id'], organization_id=org, role='viewer', can_confirm_offer=True))
        db.commit()
    headers = auth_header(viewer['token'])
    assert client.post(f"/bookings/{offer['booking_id']}/contract", headers=headers).status_code == 403
    response = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers'])
    assert response.status_code == 200, response.text
    contract = response.json(); codes = contract_otps(SessionLocal, contract['id'])
    for side in ['customer', 'supplier']:
        assert client.post(f"/contracts/{contract['id']}/sign", headers=headers, json={'side': side, 'otp': codes[f'otp_{side}']}).status_code == 403
    with SessionLocal() as db:
        assert db.query(InboxNotification).filter_by(recipient_user_id=viewer['user_id'], template='contract.otp').count() == 0
        notes = db.query(InboxNotification).filter_by(template='contract.otp').all()
        assert len(notes) == 2 and all(n.recipient_user_id == ctx['owner']['user_id'] for n in notes)
        logs = '\n'.join(r.payload for r in db.query(AuditLog).all())
        assert all(code not in logs for code in codes.values())
    room = client.get(f"/deal-room/{offer['booking_id']}", headers=headers).json()
    assert not room['can_create_contract'] and not room['can_sign_contract']


@pytest.mark.parametrize('problem', ['expired', 'cancelled', 'closed_event', 'different_quote'])
def test_new_signature_requires_current_live_contract(client, SessionLocal, problem):
    ctx, offer = prepared(client, SessionLocal)
    contract = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).json()
    codes = contract_otps(SessionLocal, contract['id'])
    with SessionLocal() as db:
        if problem == 'expired':
            db.query(BookingHold).filter_by(booking_id=offer['booking_id']).one().expires_at = now()-timedelta(seconds=1)
        elif problem == 'cancelled':
            db.get(Booking, offer['booking_id']).status = 'Cancelled'
        elif problem == 'closed_event':
            db.get(Event, ctx['event']['id']).status = 'Completed'
        else:
            db.get(Contract, contract['id']).body = 'quote_id=another-version'
        db.commit()
    response = client.post(f"/contracts/{contract['id']}/sign", headers=ctx['headers'], json={'side': 'customer', 'otp': codes['otp_customer']})
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert not db.get(Contract, contract['id']).customer_signed
        assert db.query(AuditLog).filter_by(action='contract.signed').count() == 0


def test_expired_hold_cannot_create_contract_and_signed_retry_is_a_receipt(client, SessionLocal):
    ctx, offer = prepared(client, SessionLocal)
    with SessionLocal() as db:
        h = db.query(BookingHold).filter_by(booking_id=offer['booking_id']).one()
        h.expires_at = now()-timedelta(seconds=1); db.commit()
    assert client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).status_code == 409
    with SessionLocal() as db:
        assert db.query(Contract).count() == 0
        db.query(BookingHold).filter_by(booking_id=offer['booking_id']).one().expires_at = now()+timedelta(hours=1); db.commit()
    contract = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).json()
    codes = contract_otps(SessionLocal, contract['id'])
    invalid = client.post(f"/contracts/{contract['id']}/sign", headers=ctx['headers'], json={'side': 'customer', 'otp': 'не код'})
    assert invalid.status_code == 403
    for _ in range(2):
        assert client.post(f"/contracts/{contract['id']}/sign", headers=ctx['headers'], json={'side': 'customer', 'otp': codes['otp_customer']}).status_code == 200
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='contract.signed').count() == 1
