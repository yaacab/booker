"""Recipient-indexed in-app delivery, atomic with the originating domain mutation."""
import hashlib
import json
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from booker_api.models import Booking, Contract, InboxNotification, Organization, Request, User


def notification_key(recipient, template, entity_type, entity_id, subject, body, explicit=None):
    values = [recipient, template, entity_type, entity_id, explicit] if explicit else [recipient, template, entity_type, entity_id, subject, body]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def internal_href(value):
    if not isinstance(value, str) or len(value) > 512 or not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(c) < 32 for c in value):
        return None
    parsed = urlsplit(value)
    return value if not parsed.netloc and not parsed.scheme else None


def default_href(kind, entity_id):
    try:
        UUID(entity_id)
    except (ValueError, TypeError):
        return None
    return {'event': f'/events/{entity_id}', 'booking': f'/deals/{entity_id}',
        'support_ticket': '/support', 'support_reply': '/support', 'user': '/profile'}.get(kind)


def related_href(db, item):
    if item.entity_type == 'offer':
        booking = db.query(Booking).filter_by(offer_id=item.entity_id).first()
        if booking:
            return f'/deals/{booking.id}'
    if item.entity_type == 'contract':
        contract = db.get(Contract, item.entity_id)
        if contract:
            return f'/deals/{contract.booking_id}'
    if item.entity_type == 'request':
        request = db.get(Request, item.entity_id)
        org = db.get(Organization, request.supplier_org_id) if request and request.supplier_org_id else None
        if org and org.kind in {'artist', 'venue'}:
            return f"/cabinet/{'performer' if org.kind == 'artist' else 'venue'}/requests"
    return default_href(item.entity_type, item.entity_id)


def enqueue_inbox(db, item):
    if not item.recipient_user_id or not db.get(User, item.recipient_user_id):
        return None
    key = notification_key(item.recipient_user_id, item.template, item.entity_type, item.entity_id, item.subject, item.body, item.dedupe_key)
    existing = db.query(InboxNotification).filter_by(dedupe_key=key).one_or_none()
    if existing:
        return existing
    row = InboxNotification(recipient_user_id=item.recipient_user_id, dedupe_key=key,
        template=item.template, subject=item.subject, body=item.body, entity_type=item.entity_type,
        entity_id=item.entity_id, href=internal_href(item.metadata.get('href')) or related_href(db, item))
    # sqlite3 legacy transaction mode does not BEGIN for SELECT; ensure the
    # savepoint cannot commit delivery ahead of the caller's transaction.
    connection = db.connection()
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN')
    try:
        with db.begin_nested():
            db.add(row); db.flush()
    except IntegrityError:
        existing = db.query(InboxNotification).filter_by(dedupe_key=key).one_or_none()
        if not existing:
            raise
        return existing
    return row
