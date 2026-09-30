"""Operator refund requests: independent approval and confirmed provider outcomes."""
import hashlib
import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, constr
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Payment, PaymentRefund, PaymentWebhookEvent, User
from booker_api.payments.adapter import (
    PaymentAdapterError,
    RefundOutcome,
    VerifiedRefundEvent,
    get_payment_adapter,
)
from booker_api.rate_limit import admin_sensitive_limiter, analytics_limiter, client_key
from booker_api.routers.payments import _lock_payment_context
from booker_api.security import audit, now, require_admin, require_admin_2fa

router = APIRouter(prefix='/admin/refunds', tags=['admin'])
OPEN = ('awaiting_approval', 'approved', 'submitting', 'pending', 'uncertain')
TERMINAL = ('succeeded', 'failed', 'rejected')


class ActionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    totp: str | None = None


class CreateIn(ActionIn):
    payment_id: str
    amount_rub: int | None = Field(default=None, gt=0, strict=True)
    reason: constr(strip_whitespace=True, min_length=3, max_length=2000)
    idempotency_key: constr(strip_whitespace=True, min_length=8, max_length=64)


class ExternalIn(ActionIn):
    transfer_reference: constr(strip_whitespace=True, min_length=3, max_length=255)


def sensitive(user, body, request):
    admin_sensitive_limiter.check(client_key(request, 'admin-refund'))
    if not user.totp_enabled:
        raise HTTPException(403, 'Для возврата включите второй фактор администратора')
    require_admin_2fa(user, body.totp, request)


def payload(row, payment, user):
    return {'id': row.id, 'payment_id': row.payment_id, 'amount_rub': row.amount_rub,
        'reason': row.reason, 'provider': row.provider, 'status': row.status,
        'payment_status': payment.status, 'requested_by': row.requested_by,
        'approved_by': row.approved_by, 'created_at': row.created_at,
        'approved_at': row.approved_at, 'completed_at': row.completed_at,
        'test_mode': row.provider == 'stub',
        'can_approve': row.status == 'awaiting_approval' and row.requested_by != user.id,
        'can_retry': row.status in ('approved', 'submitting', 'uncertain'),
        'can_refresh': row.status == 'pending' and row.provider != 'external',
        'can_confirm_external': row.status == 'pending' and row.provider == 'external'}


def locked(db, refund_id):
    row = db.get(PaymentRefund, refund_id)
    if not row:
        raise HTTPException(404, 'Запрос возврата не найден')
    payment = db.get(Payment, row.payment_id)
    _lock_payment_context(db, payment)
    db.refresh(row)
    return row, payment


def successful_total(db, payment_id):
    return db.query(func.coalesce(func.sum(PaymentRefund.amount_rub), 0)).filter_by(
        payment_id=payment_id, status='succeeded').scalar()


@router.get('')
def list_refunds(user: User = Depends(require_admin), db: Session = Depends(get_db),
    status: str | None = None, payment_id: str | None = None,
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    analytics_limiter.check(f'admin-refunds:{user.id}')
    query = db.query(PaymentRefund, Payment).join(Payment, Payment.id == PaymentRefund.payment_id)
    if status:
        if status not in (*OPEN, *TERMINAL):
            raise HTTPException(422, 'Неизвестное состояние возврата')
        query = query.filter(PaymentRefund.status == status)
    if payment_id:
        query = query.filter(PaymentRefund.payment_id == payment_id)
    rows = query.order_by(PaymentRefund.created_at.desc(), PaymentRefund.id).offset(offset).limit(limit + 1).all()
    return {'items': [payload(row, pay, user) for row, pay in rows[:limit]], 'has_more': len(rows) > limit}


@router.post('')
def create_refund(body: CreateIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    payment = db.get(Payment, body.payment_id)
    if not payment:
        raise HTTPException(404, 'Платёж не найден')
    _lock_payment_context(db, payment)
    key = hashlib.sha256(f'{payment.id}:{user.id}:{body.idempotency_key}'.encode()).hexdigest()
    existing = db.query(PaymentRefund).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if existing.reason != body.reason or (body.amount_rub is not None and existing.amount_rub != body.amount_rub):
            raise HTTPException(409, 'Ключ уже использован для других условий возврата')
        return payload(existing, payment, user)
    if payment.status not in ('succeeded', 'partially_refunded'):
        raise HTTPException(409, 'Возврат возможен только для подтверждённой оплаты')
    done = successful_total(db, payment.id)
    if payment.status == 'partially_refunded' and not done:
        raise HTTPException(409, 'Исторический частичный возврат требует сверки суммы оператором')
    if db.query(PaymentRefund).filter(PaymentRefund.payment_id == payment.id, PaymentRefund.status.in_(OPEN)).first():
        raise HTTPException(409, 'Для платежа уже есть незавершённый запрос возврата')
    amount = body.amount_rub if body.amount_rub is not None else payment.amount_rub - done
    if amount <= 0 or amount > payment.amount_rub - done:
        raise HTTPException(409, 'Сумма превышает доступный остаток платежа')
    row = PaymentRefund(payment_id=payment.id, amount_rub=amount, reason=body.reason,
        provider=payment.provider, requested_by=user.id, idempotency_key=key)
    db.add(row); db.flush()
    audit(db, actor_user_id=user.id, action='refund.requested', entity_type='refund', entity_id=row.id,
        payload={'payment_id': payment.id, 'amount_rub': amount, 'reason': body.reason})
    db.commit()
    return payload(row, payment, user)


def validate_approvals(db, row):
    if not row.approved_by or row.approved_by == row.requested_by:
        raise HTTPException(409, 'Нет независимого подтверждения возврата')
    for actor in (row.requested_by, row.approved_by):
        principal = db.get(User, actor)
        if principal:
            db.refresh(principal)
        if not principal or not principal.is_platform_admin or not principal.totp_enabled:
            raise HTTPException(409, 'Полномочия участников подтверждения изменились. Требуется оператор')


def apply_outcome(db, row, payment, outcome, actor_id):
    """Call only with a verified adapter result, while holding payment context locks."""
    kind = 'full' if row.amount_rub == payment.amount_rub else 'partial'
    if (outcome.amount_rub != row.amount_rub or outcome.kind != kind
        or outcome.status not in ('pending', 'failed', 'succeeded') or not outcome.refund_id
        or len(outcome.refund_id) > 255 or (row.provider_reference and row.provider_reference != outcome.refund_id)):
        raise PaymentAdapterError('Ответ возврата не соответствует запросу')
    if row.status in TERMINAL:
        if row.status != outcome.status:
            raise PaymentAdapterError('Противоречивое завершённое состояние возврата')
        return
    row.provider_reference = outcome.refund_id
    if outcome.status == 'succeeded':
        total = successful_total(db, payment.id) + row.amount_rub
        if total > payment.amount_rub:
            raise PaymentAdapterError('Возврат превышает платёж')
        payment.status = 'refunded' if total == payment.amount_rub else 'partially_refunded'
        row.completed_at = now()
        audit(db, actor_user_id=actor_id, action='payment.refunded', entity_type='payment', entity_id=payment.id,
            payload={'refund_id': row.id, 'amount_rub': row.amount_rub, 'total_refunded_rub': total,
                'requested_by': row.requested_by, 'approved_by': row.approved_by, 'provider': row.provider})
    elif outcome.status == 'failed':
        row.completed_at = now()
    row.status = outcome.status
    audit(db, actor_user_id=actor_id, action='refund.' + outcome.status, entity_type='refund', entity_id=row.id,
        payload={'payment_id': payment.id, 'amount_rub': row.amount_rub})


def save_outcome(db, row, payment, outcome, actor_id):
    # A provider refund reference may account for only one internal request,
    # including simultaneous results for different payments.
    try:
        with db.begin_nested():
            apply_outcome(db, row, payment, outcome, actor_id)
            db.flush()
    except IntegrityError:
        raise PaymentAdapterError('Этот результат возврата уже учтён') from None


def execute(db, row, payment, user):
    if row.status in TERMINAL or row.status == 'pending':
        return payload(row, payment, user)
    validate_approvals(db, row)
    adapter = get_payment_adapter()
    if adapter.name != row.provider or payment.provider != row.provider:
        raise HTTPException(409, 'Возврат должен обработать исходный платёжный партнёр')
    row.status = 'submitting'
    audit(db, actor_user_id=user.id, action='refund.submitted', entity_type='refund', entity_id=row.id)
    db.commit()  # Persist the refund identity/approval/key before contacting the provider.
    row, payment = locked(db, row.id)
    if row.status in TERMINAL or row.status == 'pending':
        return payload(row, payment, user)
    validate_approvals(db, row)
    if row.provider == 'external':
        row.status = 'pending'
        audit(db, actor_user_id=user.id, action='refund.external_pending', entity_type='refund', entity_id=row.id)
    else:
        try:
            outcome = adapter.refund(payment_id=payment.id, amount_rub=row.amount_rub,
                total_rub=payment.amount_rub, idempotency_key=row.idempotency_key)
            save_outcome(db, row, payment, outcome, user.id)
        except (PaymentAdapterError, TimeoutError, ConnectionError):
            row.status = 'uncertain'
            audit(db, actor_user_id=user.id, action='refund.uncertain', entity_type='refund', entity_id=row.id)
    db.commit()
    return payload(row, payment, user)


@router.post('/{refund_id}/approve')
def approve_refund(refund_id: str, body: ActionIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    row, payment = locked(db, refund_id)
    if row.requested_by == user.id:
        raise HTTPException(403, 'Запрос должен подтвердить другой администратор')
    if row.status != 'awaiting_approval':
        return payload(row, payment, user)
    row.approved_by = user.id; row.approved_at = now(); row.status = 'approved'
    validate_approvals(db, row)
    audit(db, actor_user_id=user.id, action='refund.approved', entity_type='refund', entity_id=row.id,
        payload={'requested_by': row.requested_by, 'amount_rub': row.amount_rub})
    db.commit()
    row, payment = locked(db, refund_id)
    return execute(db, row, payment, user)


@router.post('/{refund_id}/reject')
def reject_refund(refund_id: str, body: ActionIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    row, payment = locked(db, refund_id)
    if row.status == 'rejected':
        return payload(row, payment, user)
    if row.status != 'awaiting_approval':
        raise HTTPException(409, 'Запрос уже отправлен на исполнение')
    row.status = 'rejected'; row.completed_at = now()
    audit(db, actor_user_id=user.id, action='refund.rejected', entity_type='refund', entity_id=row.id)
    db.commit()
    return payload(row, payment, user)


@router.post('/{refund_id}/retry')
def retry_refund(refund_id: str, body: ActionIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    row, payment = locked(db, refund_id)
    if row.status == 'awaiting_approval':
        raise HTTPException(409, 'Нужно независимое подтверждение возврата')
    return execute(db, row, payment, user)


@router.post('/{refund_id}/refresh')
def refresh_refund(refund_id: str, body: ActionIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    row, payment = locked(db, refund_id)
    if row.status in TERMINAL:
        return payload(row, payment, user)
    if row.status != 'pending' or not row.provider_reference or row.provider == 'external':
        raise HTTPException(409, 'Для этого возврата сверка пока недоступна')
    adapter = get_payment_adapter()
    if adapter.name != row.provider:
        raise HTTPException(409, 'Выбран другой платёжный партнёр')
    try:
        outcome = adapter.get_refund_status(payment_id=payment.id, refund_id=row.provider_reference,
            amount_rub=row.amount_rub, total_rub=payment.amount_rub, idempotency_key=row.idempotency_key)
        save_outcome(db, row, payment, outcome, user.id)
    except (PaymentAdapterError, TimeoutError, ConnectionError):
        raise HTTPException(502, 'Партнёр не подтвердил статус возврата. Повторите сверку позже') from None
    db.commit()
    return payload(row, payment, user)


@router.post('/{refund_id}/confirm-external')
def confirm_external(refund_id: str, body: ExternalIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    sensitive(user, body, request)
    row, payment = locked(db, refund_id)
    if row.provider != 'external':
        raise HTTPException(409, 'Ручное подтверждение доступно только для перевода вне платформы')
    validate_approvals(db, row)
    if row.status == 'succeeded':
        return payload(row, payment, user)
    if row.status != 'pending':
        raise HTTPException(409, 'Возврат не ожидает подтверждения перевода')
    # Explicit operator assertion after independent approval; no invented bank event.
    try:
        save_outcome(db, row, payment, RefundOutcome(refund_id=body.transfer_reference,
            amount_rub=row.amount_rub, kind='full' if row.amount_rub == payment.amount_rub else 'partial',
            status='succeeded'), user.id)
    except PaymentAdapterError:
        raise HTTPException(409, 'Этот перевод уже учтён. Проверьте номер подтверждения') from None
    audit(db, actor_user_id=user.id, action='refund.external_confirmed', entity_type='refund', entity_id=row.id)
    db.commit()
    return payload(row, payment, user)


def apply_verified_refund_event(event, adapter, db):
    """Serialize signed refund outcomes with approval/retry and payment accounting."""
    if not isinstance(event, VerifiedRefundEvent):
        raise HTTPException(400, 'Партнёр не вернул проверенные реквизиты возврата')
    for value in (event.event_id, event.payment_id, event.request_key, event.payment_reference,
        event.refund_reference, event.merchant_id):
        if not isinstance(value, str) or not value or len(value) > 255 or value != value.strip() or any(ord(c) < 32 for c in value):
            raise HTTPException(400, 'Некорректные реквизиты уведомления')
    if type(event.amount_rub) is not int or event.amount_rub <= 0 or event.currency != 'RUB':
        raise HTTPException(409, 'Сумма или валюта уведомления не поддерживается')
    if not adapter.merchant_id or event.merchant_id != adapter.merchant_id:
        raise HTTPException(409, 'Получатель платежа не совпадает')
    if event.status not in ('pending', 'succeeded', 'failed'):
        raise HTTPException(400, 'Состояние уведомления не поддерживается')
    row = db.query(PaymentRefund).filter_by(idempotency_key=event.request_key).one_or_none()
    if not row:
        raise HTTPException(409, 'Нет сохранённого запроса возврата. Требуется сверка оператором')
    row, payment = locked(db, row.id)
    if (row.provider != adapter.name or payment.provider != adapter.name or adapter.name == 'external'
        or event.payment_id != payment.id or event.payment_reference != payment.provider_reference
        or event.amount_rub != row.amount_rub
        or (row.provider_reference and row.provider_reference != event.refund_reference)):
        raise HTTPException(409, 'Уведомление не соответствует сохранённому возврату')
    # Approval authorizes the outgoing command. A later role revocation must not
    # erase a verified money fact for an already submitted, approved command.
    if (not row.approved_by or row.approved_by == row.requested_by or not row.approved_at
        or row.status in ('awaiting_approval', 'approved', 'rejected')):
        raise HTTPException(409, 'Возврат не был подтверждён и отправлен партнёру')
    fields = asdict(event)
    fields.pop('event_id')
    fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    receipt_id = hashlib.sha256(f'refund-provider:{adapter.name}:{event.event_id}'.encode()).hexdigest()
    seen = db.get(PaymentWebhookEvent, receipt_id)
    if seen:
        if seen.payment_id != payment.id or seen.event_fingerprint != fingerprint:
            raise HTTPException(409, 'Идентификатор уведомления уже использован для других реквизитов')
        return json.loads(seen.response_json)
    receipt = PaymentWebhookEvent(event_id=receipt_id, payment_id=payment.id,
        status=event.status, event_fingerprint=fingerprint, response_json='{}')
    try:
        with db.begin_nested():
            db.add(receipt)
            db.flush()  # Claim the event before changing money, including across payments.
    except IntegrityError:
        raise HTTPException(409, 'Идентификатор уведомления уже учтён') from None
    # A delayed pending event cannot undo a terminal outcome. Contradictory
    # terminal facts require reconciliation; silently reversing them is unsafe.
    if not (row.status in TERMINAL and event.status == 'pending'):
        try:
            save_outcome(db, row, payment, RefundOutcome(refund_id=event.refund_reference,
                amount_rub=event.amount_rub, kind='full' if row.amount_rub == payment.amount_rub else 'partial',
                status=event.status), None)
        except PaymentAdapterError:
            raise HTTPException(409, 'Результат возврата требует сверки оператором') from None
    result = {'refund_id': row.id, 'payment_id': payment.id, 'status': row.status,
        'payment_status': payment.status, 'test_mode': adapter.name == 'stub'}
    receipt.response_json = json.dumps(result)
    audit(db, actor_user_id=None, action='refund.webhook', entity_type='refund', entity_id=row.id,
        payload={'payment_id': payment.id, 'provider': adapter.name, 'provider_status': event.status,
            'status': row.status, 'amount_rub': row.amount_rub})
    db.commit()
    return result
