import io
import json
import zipfile
from datetime import timedelta

from booker_api.models import (
    Booking,
    Contract,
    Event,
    Offer,
    OfferVersion,
    Organization,
    Payment,
    Request,
    Subscription,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_business_workflows import setup
from tests.test_event_readiness import venue_offer


def prepared(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    venue_offer(client, SessionLocal, ctx)
    with SessionLocal() as db:
        bookings = db.query(Booking).filter_by(event_id=ctx['event']['id']).order_by(Booking.created_at).all()
        bookings[0].status = 'Completed'; bookings[1].status = 'Confirmed'
        for index, booking in enumerate(bookings):
            db.add(Payment(booking_id=booking.id, amount_rub=12345+index, status='succeeded', provider='stub' if index == 0 else 'acquirer', idempotency_key=f'report-{index}'))
        db.get(Event, ctx['event']['id']).status = 'Completed'
        db.commit()
    ctx['report'] = f"/business/organizations/{ctx['customer']['id']}/report"
    ctx['export'] = f"/business/organizations/{ctx['customer']['id']}/documents.zip"
    return ctx


def test_actual_cohort_totals_and_hall_history(client, SessionLocal):
    ctx = prepared(client, SessionLocal)
    response = client.get(ctx['report'], headers=ctx['headers'])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['totals']['events'] == data['totals']['completed_events'] == 1
    assert data['totals']['requests'] == data['totals']['offers'] == data['totals']['confirmed'] == 2
    assert data['totals']['completed'] == 1
    assert data['totals']['confirmed_rub'] == 74200+106000
    assert data['totals']['recorded_payments_rub'] == 12346
    assert data['totals']['test_payments_rub'] == 12345
    assert len(data['suppliers']) == 2
    venue = next(s for s in data['suppliers'] if s['resource_type'] == 'venue')
    assert venue['resource_id'] == ctx['venue']['id'] and venue['hall_id'] == ctx['venue']['hall_id']
    assert venue['event_count'] == 1 and venue['events'][0]['id'] == ctx['event']['id']


def test_moscow_event_dates_and_unknown_quotes(client, SessionLocal):
    ctx = prepared(client, SessionLocal)
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id']); event.event_date = ctx['start'].replace(hour=22)
        old_version = db.query(OfferVersion).first()
        revised = OfferVersion(offer_id=old_version.offer_id, honorarium_rub=1, commission_rate=0, commission_rub=0, total_rub=1, currency='USD')
        db.add(revised); db.flush(); db.get(Offer, old_version.offer_id).active_version_id = revised.id; db.commit()
    old = ctx['start'].date().isoformat(); day = (ctx['start']+timedelta(days=1)).date().isoformat()
    empty = client.get(ctx['report']+f'?date_from={old}&date_to={old}', headers=ctx['headers']).json()
    assert empty['events'] == [] and empty['totals']['confirmed_rub'] == 0
    data = client.get(ctx['report']+f'?date_from={day}&date_to={day}', headers=ctx['headers']).json()
    assert len(data['events']) == 1 and data['totals']['confirmed_rub'] is None
    assert client.get(ctx['report']+f'?date_from={day}&date_to={old}', headers=ctx['headers']).status_code == 422
    assert client.get(ctx['report']+'?date_from=2000-01-01&date_to=2026-01-01', headers=ctx['headers']).status_code == 422


def test_export_exact_versions_contract_text_no_otp_and_no_foreign_docs(client, SessionLocal):
    ctx = prepared(client, SessionLocal)
    with SessionLocal() as db:
        booking = db.query(Booking).filter_by(event_id=ctx['event']['id']).first()
        contract = Contract(booking_id=booking.id, body='<script>alert(1)</script> Текст договора', customer_signed=True, supplier_signed=False, otp_customer='654321', otp_supplier='123456')
        db.add(contract); db.commit()
        contract_id = contract.id
        historical = OfferVersion(offer_id=booking.offer_id, honorarium_rub=40000, commission_rate=0, commission_rub=0, total_rub=40000, currency='RUB', terms='Previous immutable terms')
        db.add(historical); db.flush()
        quote_ids = {q.id for q in db.query(OfferVersion).all()}
        foreign_org = Organization(name='Other org', kind='customer'); db.add(foreign_org); db.flush()
        foreign_event = Event(organization_id=foreign_org.id, title='FOREIGN EVENT', event_date=ctx['start'], ends_at=ctx['end']); db.add(foreign_event); db.flush()
        foreign_request = Request(event_id=foreign_event.id, resource_type='artist', resource_id=ctx['artists'][0]['id'], supplier_org_id=ctx['supply']['id']); db.add(foreign_request); db.flush()
        foreign_offer = Offer(request_id=foreign_request.id); db.add(foreign_offer); db.flush()
        foreign_booking = Booking(event_id=foreign_event.id, offer_id=foreign_offer.id, slot_id=booking.slot_id); db.add(foreign_booking); db.flush()
        db.add(Contract(booking_id=foreign_booking.id, body='FOREIGN CONTRACT'))
        db.add(OfferVersion(offer_id=foreign_offer.id, honorarium_rub=1, commission_rate=0, commission_rub=0, total_rub=1, terms='FOREIGN TERMS')); db.commit()
    response = client.get(ctx['export'], headers=ctx['headers'])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['contracts'] == 1 and manifest['events'] == 1
        quotes = json.loads(archive.read('offer-versions.json'))
        assert {q['quote_id'] for q in quotes} == quote_ids
        doc = archive.read(next(n for n in archive.namelist() if contract_id in n)).decode()
        assert '&lt;script&gt;' in doc and '<script>' not in doc
        assert 'Заказчик: подписано' in doc and 'Исполнитель: не подписано' in doc
        everything = '\n'.join(archive.read(n).decode() for n in archive.namelist())
        assert '654321' not in everything and '123456' not in everything and 'PRIVATE source notes' not in everything and 'FOREIGN' not in everything
        assert all(not n.startswith('/') and '..' not in n for n in archive.namelist())


def test_auth_expiry_viewer_and_feature_controls(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    ctx = prepared(client, SessionLocal)
    outsider = register(client, 'report-outsider@booker.test')
    headers = auth_header(outsider['token'])
    assert client.get(ctx['report'], headers=headers).status_code == 403
    assert client.get(ctx['export'], headers=headers).status_code == 403
    with SessionLocal() as db:
        db.add(TeamMember(user_id=outsider['user_id'], organization_id=ctx['customer']['id'], role='viewer')); db.commit()
    assert client.get(ctx['report'], headers=headers).status_code == 200
    assert client.get(ctx['export'], headers=headers).status_code == 200
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=ctx['customer']['id']).one().current_period_end = now()-timedelta(seconds=1); db.commit()
    data = client.get(ctx['report'], headers=ctx['headers']).json()
    assert not data['enabled']['analytics'] and 'events' not in data
    assert client.get(ctx['export'], headers=ctx['headers']).status_code == 403
    monkeypatch.setattr(settings, 'customer_business', False)
    assert not client.get(ctx['report'], headers=headers).json()['enabled']['history']
