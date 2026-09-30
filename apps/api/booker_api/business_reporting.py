"""Customer reporting over actual event cohorts, never inferred revenue or new quotes."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from booker_api.event_budget import CONFIRMED, customer_amount
from booker_api.models import (
    Artist,
    AvailabilitySlot,
    Booking,
    Event,
    Offer,
    OfferVersion,
    Payment,
    Request,
    Venue,
    VenueHall,
)
from booker_api.security import aware, now

MOSCOW = ZoneInfo('Europe/Moscow')


def period(date_from=None, date_to=None):
    today = now().astimezone(MOSCOW).date()
    start = date_from or today-timedelta(days=365)
    end = date_to or today+timedelta(days=90)
    if end < start or (end-start).days > 730:
        raise HTTPException(422, 'Выберите период до двух лет; окончание не раньше начала')
    return start, end, datetime.combine(start, time.min, MOSCOW), datetime.combine(end+timedelta(days=1), time.min, MOSCOW)


def cohort(db, org_id, date_from=None, date_to=None):
    start_day, end_day, start, end = period(date_from, date_to)
    query = db.query(Event).filter(Event.organization_id == org_id, Event.event_date >= start, Event.event_date < end)
    if query.count() > 1000:
        raise HTTPException(422, 'В периоде больше 1000 событий. Уменьшите период отчёта')
    events = query.order_by(Event.event_date.desc(), Event.id).all()
    ids = [e.id for e in events]
    rows = (db.query(Request, Offer, Booking, OfferVersion, AvailabilitySlot)
        .outerjoin(Offer, Offer.request_id == Request.id)
        .outerjoin(Booking, Booking.offer_id == Offer.id)
        .outerjoin(OfferVersion, OfferVersion.id == Offer.active_version_id)
        .outerjoin(AvailabilitySlot, AvailabilitySlot.id == Booking.slot_id)
        .filter(Request.event_id.in_(ids)).order_by(Request.created_at, Request.id).all()) if ids else []
    return events, rows, {'from': start_day.isoformat(), 'to': end_day.isoformat(), 'timezone': 'Europe/Moscow', 'basis': 'event_date'}


def resource(db, req, slot):
    if req.resource_type == 'artist':
        row = db.get(Artist, req.resource_id)
        return {'key': f'artist:{req.resource_id}', 'resource_type': 'artist', 'resource_id': req.resource_id, 'hall_id': None,
            'name': row.name if row else 'Профиль артиста недоступен', 'href': f'/artists/{row.id}' if row else None}
    hall = db.get(VenueHall, req.resource_id) if req.resource_type == 'hall' else db.get(VenueHall, slot.resource_id) if slot and slot.resource_type == 'hall' else None
    venue = db.get(Venue, hall.venue_id if hall else req.resource_id)
    return {'key': f'venue:{venue.id if venue else req.resource_id}:{hall.id if hall else ""}', 'resource_type': 'venue',
        'resource_id': venue.id if venue else req.resource_id, 'hall_id': hall.id if hall else None,
        'name': f'{venue.name} · {hall.name}' if venue and hall else venue.name if venue else 'Профиль площадки недоступен',
        'href': f'/venues/{venue.id}' if venue and venue.moderation_status == 'published' else None}


def report(db, org_id, date_from=None, date_to=None):
    events, rows, selected_period = cohort(db, org_id, date_from, date_to)
    event_map = {e.id: e for e in events}
    by_event = defaultdict(list)
    for row in rows:
        by_event[row[0].event_id].append(row)
    booking_ids = {row[2].id for row in rows if row[2] and row[2].event_id == row[0].event_id}
    payments = defaultdict(list)
    for payment in db.query(Payment).filter(Payment.booking_id.in_(booking_ids)).all() if booking_ids else []:
        payments[payment.booking_id].append(payment)
    event_items, suppliers = [], {}
    for event in events:
        money = {'confirmed_rub': 0, 'recorded_payments_rub': 0, 'test_payments_rub': 0, 'pending_payments_rub': 0}
        counts = Counter()
        for req, offer, booking, version, slot in by_event[event.id]:
            counts['requests'] += 1
            counts['offers'] += bool(offer)
            if booking and booking.event_id != event.id:
                booking = None
            profile = resource(db, req, slot)
            item = suppliers.setdefault(profile['key'], {**profile, 'requests': 0, 'offers': 0, 'confirmed': 0, 'completed': 0, 'cancelled': 0, 'confirmed_rub': 0, 'events': {}, 'latest_event_date': aware(event.event_date).isoformat()})
            item['requests'] += 1; item['offers'] += bool(offer)
            item['events'][event.id] = {'id': event.id, 'title': event.title, 'event_date': aware(event.event_date).isoformat()}
            if booking:
                counts['bookings'] += 1
                counts['completed'] += booking.status == 'Completed'
                item['completed'] += booking.status == 'Completed'
                item['cancelled'] += booking.status == 'Cancelled'
                if booking.status in CONFIRMED:
                    amount = customer_amount(version)
                    counts['confirmed'] += 1; item['confirmed'] += 1
                    money['confirmed_rub'] = None if amount is None or money['confirmed_rub'] is None else money['confirmed_rub']+amount
                    item['confirmed_rub'] = None if amount is None or item['confirmed_rub'] is None else item['confirmed_rub']+amount
                for payment in payments[booking.id]:
                    if payment.status == 'succeeded':
                        if payment.provider == 'stub':
                            money['test_payments_rub'] += payment.amount_rub
                        elif payment.provider not in {'disabled', ''}:
                            money['recorded_payments_rub'] += payment.amount_rub
                    elif payment.status == 'pending' and payment.provider not in {'stub', 'disabled', ''}:
                        money['pending_payments_rub'] += payment.amount_rub
        event_items.append({'id': event.id, 'title': event.title, 'status': event.status, 'city': event.city,
            'event_date': aware(event.event_date).isoformat(), 'declared_budget_rub': event.budget_rub, **money,
            **{k: counts[k] for k in ['requests', 'offers', 'bookings', 'confirmed', 'completed']}})
    for item in suppliers.values():
        item['event_count'] = len(item['events']); item['events'] = list(item['events'].values())
    totals = {key: None if any(e[key] is None for e in event_items) else sum(e[key] for e in event_items)
        for key in ['confirmed_rub', 'recorded_payments_rub', 'test_payments_rub', 'pending_payments_rub', 'requests', 'offers', 'bookings', 'confirmed', 'completed']}
    totals['events'] = len(event_map)
    totals['completed_events'] = sum(e.status == 'Completed' for e in events)
    return {'period': selected_period, 'totals': totals, 'events': event_items,
        'suppliers': sorted(suppliers.values(), key=lambda s: (s['name'].casefold(), s['key'])),
        'methodology': 'Период выбран по датам событий по Москве. Суммы относятся ко всем записям этих событий, а не к дате движения денег. Подтверждённые условия — действующие снимки цен сделок; оплаченные записи и тестовые оплаты показаны отдельно. Это не бухгалтерский отчёт и не расчёт остатка после возвратов. История показывает обращения вашей организации, а не рейтинг поставщиков.'}
