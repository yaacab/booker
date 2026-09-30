"""Immutable acceptance deadlines; held bookings use their separate hold TTL."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import update

from booker_api.models import Booking, Event, Offer, OfferVersion
from booker_api.notifications.lifecycle import booking_notice
from booker_api.security import aware, now


def deadline(body, event):
    hours = body.get('valid_for_hours', 72)
    if type(hours) is not int or not 1 <= hours <= 720:
        raise HTTPException(400, 'Срок предложения — целое число часов от 1 до 720')
    instant = now()
    end = min(instant + timedelta(hours=hours), aware(event.event_date))
    if end <= instant:
        raise HTTPException(409, 'Событие уже началось. Уточните дату события')
    return end


def expired(version):
    return bool(version and version.valid_until and aware(version.valid_until) <= now())


def require_valid(version):
    if expired(version):
        raise HTTPException(409, 'Срок предложения истёк. Запросите новую версию условий')


def due_offers(db):
    return db.query(OfferVersion, Offer, Booking, Event).join(Offer, Offer.active_version_id == OfferVersion.id).join(
        Booking, Booking.offer_id == Offer.id).join(Event, Event.id == Booking.event_id).filter(
        Booking.status == 'Negotiation', Event.status.notin_(['Cancelled', 'Completed']),
        OfferVersion.valid_until <= now(), OfferVersion.expiry_notified_at.is_(None))


def notify_expired_offers(db, limit=100):
    count = 0
    for version, offer, booking, event in due_offers(db).order_by(OfferVersion.valid_until, OfferVersion.id).limit(limit).all():
        db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
        for row in (event, booking, offer, version):
            db.refresh(row)
        if (event.status in {'Cancelled', 'Completed'} or booking.status != 'Negotiation'
                or offer.active_version_id != version.id or version.expiry_notified_at or not expired(version)):
            continue
        booking_notice(db, booking, template='offer.expired', subject='Срок предложения истёк',
            body='Подтвердить и удержать дату по этой версии уже нельзя. Откройте сделку и согласуйте новую версию условий.', key=version.id)
        version.expiry_notified_at = now()
        count += 1
    return count
