"""Operational in-app notices tied to authoritative domain transitions."""
from booker_api.models import Event, Offer, Organization, Request, TeamMember
from booker_api.notifications.service import notify
from booker_api.notifications.types import Channel, Notification


def organization_notice(db, org_id, *, template, subject, body, entity_type, entity_id, key, href, actor_id=None):
    recipients = db.query(TeamMember.user_id).filter_by(organization_id=org_id).all()
    return notify(db, actor_user_id=actor_id, notifications=[Notification(channel=Channel.IN_APP,
        recipient_user_id=user_id, template=template, subject=subject, body=body, entity_type=entity_type,
        entity_id=entity_id, dedupe_key=key, metadata={'href': href}) for (user_id,) in recipients])


def commerce_href(db, org_id):
    org = db.get(Organization, org_id)
    path = '/cabinet/customer/business' if org and org.kind == 'customer' else '/cabinet/performer/growth' if org and org.kind == 'artist' else '/cabinet/venue/growth'
    return f'{path}?organization={org_id}'


def booking_notice(db, booking, *, template, subject, body, key, customer_only=False, event_link=False, actor_id=None):
    event = db.get(Event, booking.event_id)
    offer = db.get(Offer, booking.offer_id)
    request = db.get(Request, offer.request_id) if offer else None
    if not event or not request or request.event_id != event.id:
        return
    orgs = {event.organization_id}
    if not customer_only:
        orgs.add(request.supplier_org_id)
    for org_id in orgs:
        organization_notice(db, org_id, template=template, subject=subject, body=body,
            entity_type='booking', entity_id=booking.id, key=key,
            href=f'/events/{event.id}#event-roles' if event_link else f'/deals/{booking.id}', actor_id=actor_id)
