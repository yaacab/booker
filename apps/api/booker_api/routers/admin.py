import json
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, func, update
from sqlalchemy.orm import Session

from booker_api.analytics_taxonomy import FUNNEL_STEPS
from booker_api.av_scan import AVScanError, scan_clamd
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.disputes import ACTIVE_DISPUTE_STATUSES, create_dispute, dispute_payload
from booker_api.external_evidence import (
    append_event,
    effective_review_state,
    reserve_version,
)
from booker_api.models import (
    Artist,
    AuditLog,
    Booking,
    Conversation,
    DealAttachment,
    Dispute,
    ExternalPaymentEvent,
    ExternalPaymentReport,
    Message,
    MoneyMovement,
    Payment,
    PaymentObligation,
    ReconciliationDiscrepancy,
    ReconciliationEntry,
    ReconciliationRun,
    RefundRequest,
    User,
    Venue,
    Verification,
)
from booker_api.money_movements import append_money_movement
from booker_api.payment_scheduler import enqueue_payment_reminders
from booker_api.rate_limit import admin_sensitive_limiter, client_key
from booker_api.reconciliation import import_reconciliation_report, resolve_discrepancy
from booker_api.routers.deals import (
    _transition,
    read_verified_attachment,
)
from booker_api.schemas import (
    AttachmentScanDecisionIn,
    AttachmentScanRunIn,
    DisputeAssignmentIn,
    DisputeIn,
    DisputeResolutionIn,
    ExternalPaymentCorrectionApproveIn,
    ExternalPaymentReviewIn,
    ReconciliationImportIn,
    ReconciliationResolutionIn,
    RefundApproveIn,
    RefundRequestIn,
    VerifyIn,
)
from booker_api.security import (
    audit,
    now,
    require_admin,
    require_admin_2fa,
)
from booker_api.venue_catalog import change_partnership_status

router = APIRouter(prefix="/admin", tags=["admin"])


def _reconciliation_2fa(user: User, code: str, request: Request) -> None:
    if not user.totp_enabled:
        raise HTTPException(403, "Администратору нужен включённый второй фактор (TOTP)")
    require_admin_2fa(user, code, request)


@router.post("/reconciliation/runs")
async def import_reconciliation(
    body: ReconciliationImportIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-reconciliation-import"))
    _reconciliation_2fa(user, body.totp, request)
    if len(await request.body()) > 512_000:
        raise HTTPException(413, "Реестр превышает лимит 512 КБ")
    try:
        result = import_reconciliation_report(
            db,
            provider=body.provider,
            merchant=body.merchant,
            report_id=body.report_id,
            period_start=body.period_start,
            period_end=body.period_end,
            entries=[entry.model_dump() for entry in body.entries],
            complete=body.complete,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(
        db,
        actor_user_id=user.id,
        action="reconciliation.report_imported",
        entity_type="reconciliation_run",
        entity_id=result["run_id"],
        payload={"status": result["status"], "idempotent": result.get("idempotent", False), "conflict": result.get("conflict", False)},
    )
    db.commit()
    if result.get("conflict"):
        raise HTTPException(409, "report_id повторно использован с другим содержимым")
    return result


@router.get("/reconciliation/runs")
def list_reconciliation_runs(
    request: Request,
    limit: int = 50,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-reconciliation-read"))
    _reconciliation_2fa(user, "", request)
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit должен быть от 1 до 100")
    rows = db.query(ReconciliationRun).order_by(ReconciliationRun.received_at.desc(), ReconciliationRun.id.desc()).limit(limit).all()
    return {"items": [{"id": row.id, "provider": row.provider, "merchant": row.merchant, "report_id": row.report_id, "period_start": row.period_start, "period_end": row.period_end, "status": row.status, "failure_reason": row.failure_reason, "received_at": row.received_at, "completed_at": row.completed_at} for row in rows]}


@router.get("/reconciliation/discrepancies")
def list_reconciliation_discrepancies(
    request: Request,
    limit: int = 100,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-reconciliation-read"))
    _reconciliation_2fa(user, "", request)
    if not 1 <= limit <= 200:
        raise HTTPException(422, "limit должен быть от 1 до 200")
    rows = db.query(ReconciliationDiscrepancy).filter_by(status="open").order_by(ReconciliationDiscrepancy.created_at.asc(), ReconciliationDiscrepancy.id.asc()).limit(limit).all()
    return {"items": [{"id": row.id, "run_id": row.run_id, "kind": row.kind, "booking_id": row.booking_id, "payment_id": row.payment_id, "movement_id": row.movement_id, "entry_id": row.entry_id, "status": row.status, "created_at": row.created_at} for row in rows]}


@router.get("/reconciliation/discrepancies/{discrepancy_id}")
def reconciliation_discrepancy_detail(
    discrepancy_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-reconciliation-read"))
    _reconciliation_2fa(user, "", request)
    row = db.get(ReconciliationDiscrepancy, discrepancy_id)
    if row is None:
        raise HTTPException(404, "Расхождение не найдено")
    run = db.get(ReconciliationRun, row.run_id)
    entry = db.get(ReconciliationEntry, row.entry_id) if row.entry_id else None
    movement = db.get(MoneyMovement, row.movement_id) if row.movement_id else None
    return {
        "id": row.id, "run_id": row.run_id, "kind": row.kind, "status": row.status,
        "provider": run.provider, "merchant": run.merchant, "report_id": run.report_id,
        "booking_id": row.booking_id, "payment_id": row.payment_id,
        "entry": {"id": entry.id, "operation_kind": entry.operation_kind, "amount_rub": entry.amount_rub, "currency": entry.currency, "provider_status": entry.provider_status, "occurred_at": entry.occurred_at, "provider_operation_id": entry.provider_operation_id, "provider_reference": entry.provider_reference} if entry else None,
        "movement": {"id": movement.id, "kind": movement.kind, "amount_rub": movement.amount_rub, "currency": movement.currency, "created_at": movement.created_at} if movement else None,
        "details": json.loads(row.details_json),
        "resolution": row.resolution, "resolved_by_user_id": row.resolved_by_user_id,
        "resolved_at": row.resolved_at,
    }


@router.post("/reconciliation/discrepancies/{discrepancy_id}/resolve")
def resolve_reconciliation_discrepancy(
    discrepancy_id: str,
    body: ReconciliationResolutionIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-reconciliation-resolve"))
    _reconciliation_2fa(user, body.totp, request)
    row = db.query(ReconciliationDiscrepancy).filter_by(id=discrepancy_id).with_for_update().one_or_none()
    if row is None:
        raise HTTPException(404, "Расхождение не найдено")
    if row.status == "resolved":
        if row.resolution != body.resolution.strip():
            raise HTTPException(409, "Расхождение уже закрыто с другим основанием")
        return {"id": row.id, "status": row.status, "idempotent": True}
    try:
        resolve_discrepancy(db, row, actor_user_id=user.id, resolution=body.resolution)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, actor_user_id=user.id, action="reconciliation.discrepancy_resolved", entity_type="reconciliation_discrepancy", entity_id=row.id, payload={"run_id": row.run_id, "reason": row.resolution})
    db.commit()
    return {"id": row.id, "status": row.status, "idempotent": False}

PILOT_ACTIONS = (
    "request.created",
    "offer.created",
    "workspace.switched",
    "service.created",
    "hall.created",
    "client.event",
)


def _action_metrics(db: Session, since, action: str) -> dict:
    base = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.action == action)
    unique = (
        db.query(func.count(func.distinct(AuditLog.entity_id)))
        .filter(
            AuditLog.created_at >= since,
            AuditLog.action == action,
            AuditLog.entity_id != "",
        )
        .scalar()
        or 0
    )
    return {"count": base.count(), "unique_entities": unique}


def _payment_metrics(db: Session, since) -> dict:
    base = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.action.like("payment.%"))
    unique = (
        db.query(func.count(func.distinct(AuditLog.entity_id)))
        .filter(
            AuditLog.created_at >= since,
            AuditLog.action.like("payment.%"),
            AuditLog.entity_id != "",
        )
        .scalar()
        or 0
    )
    by_action = {
        action: count
        for action, count in db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since, AuditLog.action.like("payment.%"))
        .group_by(AuditLog.action)
        .all()
    }
    return {"count": base.count(), "unique_entities": unique, "by_action": by_action}


def _client_event_metrics(db: Session, since) -> dict:
    base = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.action == "client.event")
    unique = (
        db.query(func.count(func.distinct(AuditLog.actor_user_id)))
        .filter(
            AuditLog.created_at >= since,
            AuditLog.action == "client.event",
            AuditLog.actor_user_id.isnot(None),
        )
        .scalar()
        or 0
    )
    by_event: dict[str, int] = {}
    for row in base.all():
        try:
            payload = json.loads(row.payload or "{}")
        except json.JSONDecodeError:
            payload = {}
        name = str(payload.get("name") or "unknown")
        by_event[name] = by_event.get(name, 0) + 1
    return {"count": base.count(), "unique_entities": unique, "by_event": by_event}


def _client_event_name(row: AuditLog) -> str:
    try:
        payload = json.loads(row.payload or "{}")
    except json.JSONDecodeError:
        return ""
    return str(payload.get("name") or "")


def _audit_count(db: Session, since, action: str, entity_id: str | None = None) -> int:
    q = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.action == action)
    if entity_id is not None:
        if action == "client.event":
            return sum(1 for row in q.all() if _client_event_name(row) == entity_id)
        q = q.filter(AuditLog.entity_id == entity_id)
    return q.count()


def _funnel_dashboard(db: Session, since) -> dict:
    steps: list[dict] = []
    prev_count: int | None = None
    for key, action, entity_id in FUNNEL_STEPS:
        count = _audit_count(db, since, action, entity_id)
        conversion = round(count / prev_count * 100, 1) if prev_count and prev_count > 0 else None
        steps.append({"step": key, "count": count, "conversion_from_prev_pct": conversion})
        prev_count = count
    return {"steps": steps}


def _liquidity_dashboard(db: Session, since) -> dict:
    searches = _audit_count(db, since, "client.event", "search.performed")
    deal_opens = _audit_count(db, since, "client.event", "deal.room.opened")
    requests = _audit_count(db, since, "request.created")
    offers = _audit_count(db, since, "offer.created")
    return {
        "search_to_deal_pct": round(deal_opens / searches * 100, 1) if searches else None,
        "offer_response_pct": round(offers / requests * 100, 1) if requests else None,
        "searches": searches,
        "deal_opens": deal_opens,
        "requests": requests,
        "offers": offers,
    }


def _leakage_dashboard(db: Session, since) -> dict:
    studio_started = _audit_count(db, since, "client.event", "event.studio.started")
    studio_completed = _audit_count(db, since, "client.event", "event.studio.completed")
    requests = _audit_count(db, since, "request.created")
    offers = _audit_count(db, since, "offer.created")
    holds = _audit_count(db, since, "hold.created")
    holds_expired = _audit_count(db, since, "hold.expired")
    contracts = _audit_count(db, since, "contract.draft_acknowledged")
    return {
        "studio_abandoned": max(studio_started - studio_completed, 0),
        "unanswered_requests": max(requests - offers, 0),
        "holds_expired": holds_expired,
        "holds_without_contract": max(holds - contracts, 0),
    }


def _dashboards(db: Session, since) -> dict:
    return {
        "funnel": _funnel_dashboard(db, since),
        "liquidity": _liquidity_dashboard(db, since),
        "leakage": _leakage_dashboard(db, since),
    }


def _period_metrics(db: Session, days: int) -> dict:
    since = now() - timedelta(days=days)
    metrics = {action: _action_metrics(db, since, action) for action in PILOT_ACTIONS if action != "client.event"}
    metrics["client.event"] = _client_event_metrics(db, since)
    metrics["payment"] = _payment_metrics(db, since)
    metrics["dashboards"] = _dashboards(db, since)
    return metrics


@router.get("/verifications")
def list_verifications(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Verification).filter(Verification.status == "queued").all()
    pending_artists = db.query(Artist).filter(Artist.verified_status == "pending").all()
    pending_venues = db.query(Venue).filter(Venue.verified_status == "pending").all()
    return {
        "queue": [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id} for r in rows],
        "artists": [{"id": a.id, "name": a.name, "status": a.verified_status} for a in pending_artists],
        "venues": [{"id": v.id, "name": v.name, "status": v.verified_status} for v in pending_venues],
    }


@router.post("/verifications")
def decide_verification(
    body: VerifyIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.target_type == "artist":
        target = db.get(Artist, body.target_id)
    else:
        target = db.get(Venue, body.target_id)
    if not target:
        raise HTTPException(404, "Цель верификации не найдена")
    if isinstance(target, Venue):
        fallback_status = (
            "unverified_listing"
            if target.source_type == "automated_import"
            else "claimed"
        )
        change_partnership_status(
            db,
            target,
            "verified" if body.approve else fallback_status,
            changed_by=user.id,
            comment=body.notes,
        )
        target.verified_status = "approved" if body.approve else "rejected"
    else:
        target.verified = body.approve
        target.verified_status = "approved" if body.approve else "rejected"
    row = Verification(
        target_type=body.target_type,
        target_id=body.target_id,
        status="approved" if body.approve else "rejected",
        notes=body.notes,
    )
    db.add(row)
    audit(
        db,
        actor_user_id=user.id,
        action="verification.decided",
        entity_type=body.target_type,
        entity_id=body.target_id,
    )
    db.commit()
    return {"verified": target.verified}


@router.post("/disputes")
def open_dispute(
    booking_id: str,
    body: DisputeIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().one_or_none()
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    dispute = create_dispute(
        db,
        booking=booking,
        category=body.category,
        notes=body.notes,
        actor_user_id=user.id,
    )
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.opened",
        entity_type="dispute",
        entity_id=dispute.id,
        payload={
            "booking_id": booking.id,
            "category": body.category,
            "priority": dispute.priority,
            "response_due_at": dispute.response_due_at.isoformat(),
            "note": "AI не выносит решений по спорам",
        },
    )
    db.commit()
    db.refresh(dispute)
    return {**dispute_payload(db, dispute, include_internal=True), "ai_decides": False}


@router.get("/disputes")
def list_disputes(
    dispute_status: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if dispute_status and dispute_status not in {"open", "in_review", "resolved"}:
        raise HTTPException(400, "Неизвестный статус спора")
    query = db.query(Dispute)
    if dispute_status:
        query = query.filter(Dispute.status == dispute_status)
    rows = (
        query.order_by(
            case(
                (Dispute.status == "open", 0),
                (Dispute.status == "in_review", 1),
                (Dispute.status == "resolved", 2),
                else_=9,
            ),
            Dispute.response_due_at.asc(),
            Dispute.created_at.asc(),
            Dispute.id.asc(),
        )
        .limit(200)
        .all()
    )
    return {"items": [dispute_payload(db, row, include_internal=True) for row in rows]}


@router.put("/disputes/{dispute_id}/assignment")
def assign_dispute(
    dispute_id: str,
    body: DisputeAssignmentIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-dispute-assignment"))
    require_admin_2fa(user, body.totp, request)
    assignee = db.get(User, body.assignee_user_id)
    if not assignee or not assignee.is_platform_admin:
        raise HTTPException(400, "Исполнитель должен быть администратором платформы")
    claimed = db.execute(
        update(Dispute)
        .where(
            Dispute.id == dispute_id,
            Dispute.status.in_(ACTIVE_DISPUTE_STATUSES),
            Dispute.state_version == body.state_version,
        )
        .values(
            assigned_to_user_id=assignee.id,
            status="in_review",
            state_version=Dispute.state_version + 1,
        )
    ).rowcount
    if claimed != 1:
        dispute = db.get(Dispute, dispute_id)
        if not dispute:
            raise HTTPException(404, "Спор не найден")
        if dispute.status not in ACTIVE_DISPUTE_STATUSES:
            raise HTTPException(409, "Спор уже закрыт")
        raise HTTPException(409, "Спор уже изменён, обновите очередь")
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.assigned",
        entity_type="dispute",
        entity_id=dispute_id,
        payload={"assigned_to_user_id": assignee.id, "from_version": body.state_version},
    )
    db.commit()
    db.expire_all()
    return dispute_payload(db, db.get(Dispute, dispute_id), include_internal=True)


@router.put("/disputes/{dispute_id}/resolve")
def resolve_dispute(
    dispute_id: str,
    body: DisputeResolutionIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-dispute-resolution"))
    require_admin_2fa(user, body.totp, request)
    moment = now()
    claimed = db.execute(
        update(Dispute)
        .where(
            Dispute.id == dispute_id,
            Dispute.status.in_(ACTIVE_DISPUTE_STATUSES),
            Dispute.assigned_to_user_id == user.id,
            Dispute.state_version == body.state_version,
        )
        .values(
            status="resolved",
            decision_kind=body.decision_kind,
            decision=body.decision_note.strip(),
            resolved_by_user_id=user.id,
            resolved_at=moment,
            state_version=Dispute.state_version + 1,
        )
    ).rowcount
    if claimed != 1:
        dispute = db.get(Dispute, dispute_id)
        if not dispute:
            raise HTTPException(404, "Спор не найден")
        if dispute.status not in ACTIVE_DISPUTE_STATUSES:
            raise HTTPException(409, "Спор уже закрыт")
        if dispute.assigned_to_user_id != user.id:
            raise HTTPException(403, "Решить спор может только назначенный оператор")
        raise HTTPException(409, "Спор уже изменён, обновите очередь")
    dispute = db.get(Dispute, dispute_id)
    booking = db.get(Booking, dispute.booking_id)
    if booking.status == "Dispute":
        _transition(booking, "Resolved")
    conversation = (
        db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    )
    if conversation:
        db.add(
            Message(
                conversation_id=conversation.id,
                kind="system",
                body="Оператор завершил рассмотрение спора. Денежные действия оформляются отдельно.",
            )
        )
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.resolved",
        entity_type="dispute",
        entity_id=dispute_id,
        payload={
            "booking_id": booking.id,
            "decision_kind": body.decision_kind,
            "from_version": body.state_version,
            "automatic_money_movement": False,
        },
    )
    db.commit()
    db.expire_all()
    result = dispute_payload(db, db.get(Dispute, dispute_id), include_internal=True)
    result["requires_separate_refund_request"] = body.decision_kind == "refund_review_required"
    result["automatic_money_movement"] = False
    return result


@router.post("/refunds")
def create_refund_request(
    body: RefundRequestIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-refund"))
    require_admin_2fa(user, body.totp, request)
    payment = (
        db.query(Payment)
        .filter(Payment.id == body.payment_id)
        .with_for_update()
        .one_or_none()
    )
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if payment.status == "refunded":
        return {"id": payment.id, "status": payment.status, "idempotent": True}
    if payment.status == "partially_refunded":
        raise HTTPException(409, "Для следующего возврата нужен расчёт остатка и отдельное основание")
    if payment.status != "succeeded":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Возврат возможен только для успешного платежа",
        )
    existing = (
        db.query(RefundRequest)
        .filter(
            RefundRequest.payment_id == payment.id,
            RefundRequest.status.in_(("pending", "processing")),
        )
        .one_or_none()
    )
    if existing:
        if existing.status == "processing":
            raise HTTPException(409, "Возврат уже обрабатывается")
        return {
            "id": existing.id,
            "payment_id": payment.id,
            "status": existing.status,
            "idempotent": True,
        }
    refund_request = RefundRequest(
        payment_id=payment.id,
        requested_by_user_id=user.id,
        amount_rub=payment.amount_rub,
        reason=body.reason,
    )
    db.add(refund_request)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="payment.refund_requested",
        entity_type="refund_request",
        entity_id=refund_request.id,
        payload={
            "payment_id": payment.id,
            "amount_rub": payment.amount_rub,
            "reason": body.reason,
        },
    )
    db.commit()
    return {"id": refund_request.id, "payment_id": payment.id, "status": refund_request.status}


@router.post("/refunds/{refund_request_id}/approve")
def approve_refund_request(
    refund_request_id: str,
    body: RefundApproveIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-refund"))
    require_admin_2fa(user, body.totp, request)
    refund_request = (
        db.query(RefundRequest)
        .filter(RefundRequest.id == refund_request_id)
        .with_for_update()
        .one_or_none()
    )
    if not refund_request:
        raise HTTPException(404, "Заявка на возврат не найдена")
    if refund_request.requested_by_user_id == user.id:
        raise HTTPException(403, "Возврат требует второго администратора")
    payment = (
        db.query(Payment)
        .filter(Payment.id == refund_request.payment_id)
        .with_for_update()
        .one_or_none()
    )
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if refund_request.status == "refunded" and payment.status in {"refunded", "partially_refunded"}:
        return {"id": payment.id, "status": payment.status, "refund_request_id": refund_request.id, "idempotent": True}
    if refund_request.status != "pending":
        raise HTTPException(409, "Заявка на возврат уже рассмотрена")
    if payment.status != "succeeded":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Возврат возможен только для успешного платежа",
        )
    if not 0 < refund_request.amount_rub <= payment.amount_rub:
        raise HTTPException(409, "Сумма заявки на возврат не соответствует платежу")
    from booker_api.payments.adapter import (
        PaymentAdapterError,
        get_refund_adapter_for_payment,
    )

    try:
        adapter = get_refund_adapter_for_payment(
            payment_provider=payment.provider,
            provider_merchant=payment.provider_merchant,
        )
    except PaymentAdapterError as exc:
        raise HTTPException(400, str(exc)) from exc
    payment_id = payment.id
    refund_request_id = refund_request.id
    refund_amount_rub = refund_request.amount_rub
    payment_amount_rub = payment.amount_rub
    refund_key = f"refund-{refund_request_id}"
    claimed = db.execute(
        update(RefundRequest)
        .where(RefundRequest.id == refund_request_id, RefundRequest.status == "pending")
        .values(status="processing")
    ).rowcount
    if claimed != 1:
        db.expire(refund_request)
        db.refresh(refund_request)
        if refund_request.status == "refunded" and payment.status in {
            "refunded",
            "partially_refunded",
        }:
            return {
                "id": payment.id,
                "status": payment.status,
                "refund_request_id": refund_request.id,
                "idempotent": True,
            }
        raise HTTPException(409, "Заявка на возврат уже обрабатывается")
    refund_request.status = "processing"
    audit(
        db,
        actor_user_id=user.id,
        action="payment.refund_dispatch_started",
        entity_type="refund_request",
        entity_id=refund_request_id,
        payload={
            "payment_id": payment_id,
            "provider": payment.provider,
            "merchant": payment.provider_merchant,
            "amount_rub": refund_amount_rub,
            "idempotency_key": refund_key,
        },
    )
    # Persist the dispatch intent before crossing the provider boundary. If the
    # provider succeeds but finalization fails, retries see processing and
    # cannot issue a second refund without independent reconciliation.
    db.commit()

    try:
        outcome = adapter.refund(
            payment_id=payment_id,
            amount_rub=refund_amount_rub,
            total_rub=payment_amount_rub,
            idempotency_key=refund_key,
        )
    except PaymentAdapterError as exc:
        raise HTTPException(409, "Исход возврата требует сверки с партнёром") from exc
    expected_kind = "full" if refund_amount_rub == payment_amount_rub else "partial"
    if (
        outcome.status != "succeeded"
        or outcome.amount_rub != refund_amount_rub
        or outcome.kind != expected_kind
        or not outcome.refund_id
    ):
        raise HTTPException(409, "Исход возврата требует сверки с партнёром")
    db.expire_all()
    refund_request = (
        db.query(RefundRequest)
        .filter(RefundRequest.id == refund_request_id)
        .with_for_update()
        .one()
    )
    payment = (
        db.query(Payment)
        .filter(Payment.id == refund_request.payment_id)
        .with_for_update()
        .one()
    )
    if refund_request.status != "processing" or payment.status != "succeeded":
        raise HTTPException(409, "Состояние возврата изменилось; требуется сверка")
    payment.status = "refunded" if outcome.kind == "full" else "partially_refunded"
    refund_request.status = "refunded"
    refund_request.approved_by_user_id = user.id
    refund_request.refund_id = outcome.refund_id
    refund_request.approved_at = now()
    append_money_movement(
        db,
        payment=payment,
        kind="refund",
        direction="debit",
        amount_rub=outcome.amount_rub,
        source_type="provider_refund",
        source_id=f"{payment.provider}:{outcome.refund_id}",
        actor_user_id=user.id,
        metadata={
            "refund_request_id": refund_request.id,
            "refund_kind": outcome.kind,
            "requested_by_user_id": refund_request.requested_by_user_id,
        },
    )
    audit(
        db,
        actor_user_id=user.id,
        action="payment.refunded",
        entity_type="payment",
        entity_id=payment.id,
        payload={
            "refund_request_id": refund_request.id,
            "requested_by_user_id": refund_request.requested_by_user_id,
            "reason": refund_request.reason,
            "refund_id": outcome.refund_id,
            "amount_rub": outcome.amount_rub,
            "kind": outcome.kind,
        },
    )
    db.commit()
    return {"id": payment.id, "status": payment.status, "refund_request_id": refund_request.id}


@router.post("/attachments/{attachment_id}/scan-decision")
def decide_attachment_scan(
    attachment_id: str,
    body: AttachmentScanDecisionIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-attachment-scan"))
    require_admin_2fa(user, body.totp, request)
    row = db.get(DealAttachment, attachment_id)
    if not row:
        raise HTTPException(404, "Вложение не найдено")
    if body.scan_status == "clean" and settings.av_provider == "clamd":
        raise HTTPException(409, "Ручной статус clean выключен при включённом AV")
    if row.scan_status == body.scan_status:
        if body.scan_status == "clean":
            read_verified_attachment(row)
        return {"id": row.id, "scan_status": row.scan_status, "idempotent": True}
    if row.scan_status not in {"quarantined", "clean", "blocked"}:
        raise HTTPException(409, "Неизвестный статус проверки вложения")
    if body.scan_status == "clean":
        read_verified_attachment(row)
    row.scan_status = body.scan_status
    row.scan_note = body.note
    row.av_verdict_provider = None
    row.av_verdict_sha256 = None
    row.av_scan_token = None
    row.av_scan_started_at = None
    row.scanned_by_user_id = user.id
    row.scanned_at = now()
    audit(
        db,
        actor_user_id=user.id,
        action="attachment.scan_decided",
        entity_type="attachment",
        entity_id=row.id,
        payload={"scan_status": row.scan_status, "booking_id": row.booking_id},
    )
    db.commit()
    return {"id": row.id, "scan_status": row.scan_status}


@router.post("/attachments/{attachment_id}/scan")
def run_attachment_av_scan(
    attachment_id: str,
    body: AttachmentScanRunIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_sensitive_limiter.check(client_key(request, "admin-attachment-scan"))
    require_admin_2fa(user, body.totp, request)
    if settings.av_provider != "clamd":
        raise HTTPException(409, "AV-сканер не настроен")
    row = db.get(DealAttachment, attachment_id)
    if not row:
        raise HTTPException(404, "Вложение не найдено")
    attempt = str(uuid4())
    started_at = now()
    stale_before = started_at - timedelta(seconds=max(30.0, settings.av_timeout_seconds * 2))
    # Quarantine before network I/O so an old manual clean verdict cannot be
    # downloaded while the configured scanner is unavailable or still working.
    started = db.execute(
        update(DealAttachment)
        .where(
            DealAttachment.id == row.id,
            DealAttachment.scan_status.in_(["quarantined", "clean"]),
            (DealAttachment.av_scan_token.is_(None))
            | (DealAttachment.av_scan_started_at <= stale_before),
        )
        .values(
            scan_status="quarantined",
            av_verdict_provider=None,
            av_verdict_sha256=None,
            av_scan_token=attempt,
            av_scan_started_at=started_at,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    if started != 1:
        db.rollback()
        raise HTTPException(409, "Вложение заблокировано или уже проверяется")
    db.commit()
    db.refresh(row)

    def release_attempt(*, block: bool = False) -> None:
        values: dict = {"av_scan_token": None, "av_scan_started_at": None}
        if block:
            values["scan_status"] = "blocked"
        changed = db.execute(
            update(DealAttachment)
            .where(DealAttachment.id == row.id, DealAttachment.av_scan_token == attempt)
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed == 1 and block:
            audit(
                db,
                actor_user_id=user.id,
                action="attachment.integrity_failed",
                entity_type="attachment",
                entity_id=row.id,
                payload={"booking_id": row.booking_id},
            )
        db.commit()

    try:
        raw = read_verified_attachment(row)
    except HTTPException as exc:
        release_attempt(block=exc.status_code == 409)
        raise
    try:
        result = scan_clamd(
            raw,
            socket_path=settings.av_clamd_socket,
            timeout_seconds=settings.av_timeout_seconds,
        )
    except AVScanError as exc:
        release_attempt()
        raise HTTPException(503, "AV-сканер недоступен; файл остаётся в карантине") from exc
    changed = db.execute(
        update(DealAttachment)
        .where(
            DealAttachment.id == row.id,
            DealAttachment.scan_status == "quarantined",
            DealAttachment.av_scan_token == attempt,
        )
        .values(
            scan_status=result,
            scan_note=f"clamd: {result}",
            av_verdict_provider="clamd",
            av_verdict_sha256=row.sha256,
            av_scan_token=None,
            av_scan_started_at=None,
            scanned_by_user_id=user.id,
            scanned_at=now(),
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "Решение по вложению изменилось во время проверки")
    audit(
        db,
        actor_user_id=user.id,
        action="attachment.av_scanned",
        entity_type="attachment",
        entity_id=row.id,
        payload={"scan_status": result, "booking_id": row.booking_id, "provider": "clamd"},
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "scan_status": result, "provider": "clamd"}


@router.post("/payments/{payment_id}/confirm-external")
def confirm_external_payment(
    payment_id: str,
    body: ExternalPaymentReviewIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    totp: str | None = None,
):
    """Record an operator-reviewed transfer report; never capture platform funds."""
    admin_sensitive_limiter.check(client_key(request, "admin-external-pay"))
    require_admin_2fa(user, totp, request)
    if settings.payment_provider.strip().lower() != "external":
        raise HTTPException(403, "Доступно только при BOOKER_PAYMENT_PROVIDER=external")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if payment.provider != "external":
        raise HTTPException(409, "Платёж не в режиме external")
    report = db.get(ExternalPaymentReport, body.report_id)
    if not report or report.payment_id != payment.id:
        raise HTTPException(404, "Сведения о переводе не найдены")
    if report.status == "recorded" and payment.status == "external_recorded":
        if db.query(ExternalPaymentEvent).filter_by(
            report_id=report.id, kind="correction_approved"
        ).first():
            raise HTTPException(409, "Сведения позднее исправлены")
        return {"id": payment.id, "status": payment.status, "report_id": report.id, "idempotent": True}
    if not body.recipient_confirmed:
        raise HTTPException(409, "Нужно подтверждение получателя перевода")
    if payment.status != "pending" or report.status != "submitted":
        raise HTTPException(409, "Сведения или платёж уже рассмотрены")
    latest = (
        db.query(ExternalPaymentReport)
        .filter_by(payment_id=payment.id)
        .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
        .first()
    )
    if latest.id != report.id:
        raise HTTPException(409, "Есть более поздние сведения о переводе")
    recipient_ack = db.query(ExternalPaymentEvent).filter_by(
        report_id=report.id, kind="recipient_acknowledged"
    ).one_or_none()
    if not recipient_ack or recipient_ack.actor_user_id == user.id:
        raise HTTPException(409, "Нужно отдельное подтверждение получателя")
    booking = db.get(Booking, payment.booking_id)
    obligation = db.get(PaymentObligation, payment.obligation_id) if payment.obligation_id else None
    allowed_booking_status = (
        booking and booking.status == "AwaitingPayment"
        if not obligation or obligation.kind == "advance"
        else booking and booking.status in {"Confirmed", "InProgress"}
    )
    if not booking or not allowed_booking_status:
        raise HTTPException(409, "Бронь не ожидает внешнего перевода")
    report.status = "recorded"
    report.reviewed_by_user_id = user.id
    report.review_note = body.review_note.strip()
    report.reviewed_at = now()
    version = payment.external_evidence_version or 0
    reserve_version(db, payment, version)
    payment.status = "external_recorded"
    review_event = append_event(
        db, payment=payment, report_id=report.id, kind="admin_evidence_reviewed",
        idempotency_key=f"admin-review:{report.id}", expected_version=version,
        actor_user_id=user.id, parent_event_id=recipient_ack.id,
    )
    conv = db.query(Conversation).filter_by(booking_id=booking.id).one_or_none()
    if conv:
        message = "Оператор проверил сведения сторон о внешнем переводе. Банковское зачисление не подтверждено."
        db.add(Message(conversation_id=conv.id, kind="system", body=message))
    audit(
        db,
        actor_user_id=user.id,
        action="payment.external_recorded",
        entity_type="payment",
        entity_id=payment.id,
        payload={
            "report_id": report.id,
            "recipient_ack_event_id": recipient_ack.id,
            "review_event_id": review_event.id,
            "obligation_id": obligation.id if obligation else None,
            "obligation_kind": obligation.kind if obligation else "legacy",
        },
    )
    db.commit()
    return {"id": payment.id, "status": payment.status, "report_id": report.id,
            "booking_status": booking.status, "reliable_money_fact": False,
            "evidence_version": version + 1}


@router.post("/payments/{payment_id}/request-external-clarification")
def request_external_clarification(
    payment_id: str,
    body: ExternalPaymentReviewIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    totp: str | None = None,
):
    admin_sensitive_limiter.check(client_key(request, "admin-external-pay"))
    require_admin_2fa(user, totp, request)
    payment = db.get(Payment, payment_id)
    report = db.get(ExternalPaymentReport, body.report_id)
    if not payment or payment.provider != "external" or not report or report.payment_id != payment.id:
        raise HTTPException(404, "Сведения о внешнем переводе не найдены")
    if report.status == "needs_clarification":
        return {"id": report.id, "status": report.status, "idempotent": True}
    if payment.status != "pending" or report.status != "submitted":
        raise HTTPException(409, "Сведения уже рассмотрены")
    report.status = "needs_clarification"
    report.reviewed_by_user_id = user.id
    report.review_note = body.review_note.strip()
    report.reviewed_at = now()
    booking = db.get(Booking, payment.booking_id)
    conv = db.query(Conversation).filter_by(booking_id=booking.id).one_or_none()
    if conv:
        db.add(Message(conversation_id=conv.id, kind="system", body="Оператор запросил уточнение по внешнему переводу. Бронирование ожидает проверки; проверьте сведения в разделе оплаты."))
    audit(db, actor_user_id=user.id, action="payment.external_clarification_requested", entity_type="payment", entity_id=payment.id, payload={"report_id": report.id})
    db.commit()
    return {"id": report.id, "status": report.status, "payment_status": payment.status}


@router.get("/payments/{payment_id}/external-reports")
def list_external_reports(
    payment_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    totp: str | None = None,
):
    admin_sensitive_limiter.check(client_key(request, "admin-external-pay"))
    require_admin_2fa(user, totp, request)
    payment = db.get(Payment, payment_id)
    if not payment or payment.provider != "external":
        raise HTTPException(404, "Внешний платёж не найден")
    rows = db.query(ExternalPaymentReport).filter_by(payment_id=payment.id).order_by(ExternalPaymentReport.created_at.desc()).all()
    events = (db.query(ExternalPaymentEvent).filter_by(payment_id=payment.id)
              .order_by(ExternalPaymentEvent.created_at.asc(), ExternalPaymentEvent.id.asc()).all())
    return {
        "payment_id": payment.id,
        "payment_status": payment.status,
        "evidence_version": payment.external_evidence_version or 0,
        "reliable_money_fact": False,
        "effective_state": effective_review_state(events, rows[0].status, rows[0].id) if rows else None,
        "reports": [{"id": r.id, "status": r.status, "reference": r.reference,
                     "details": r.details, "submitted_by_user_id": r.submitted_by_user_id,
                     "reviewed_by_user_id": r.reviewed_by_user_id, "review_note": r.review_note,
                     "created_at": r.created_at.isoformat()} for r in rows],
        "timeline": [{"id": e.id, "report_id": e.report_id, "kind": e.kind,
                      "parent_event_id": e.parent_event_id, "reason_code": e.reason_code,
                      "actor_user_id": e.actor_user_id, "created_at": e.created_at.isoformat()}
                     for e in events],
    }


@router.post("/payments/{payment_id}/external-corrections/approve")
def approve_external_correction(
    payment_id: str,
    body: ExternalPaymentCorrectionApproveIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    totp: str | None = None,
):
    admin_sensitive_limiter.check(client_key(request, "admin-external-correction"))
    require_admin_2fa(user, totp, request)
    payment = db.get(Payment, payment_id)
    if not payment or payment.provider != "external":
        raise HTTPException(404, "Внешний платёж не найден")
    requested = db.get(ExternalPaymentEvent, body.request_event_id)
    if not requested or requested.payment_id != payment.id or requested.kind != "correction_requested":
        raise HTTPException(404, "Запрос исправления не найден")
    report = db.get(ExternalPaymentReport, requested.report_id)
    if not report or report.payment_id != payment.id:
        raise HTTPException(409, "Отчёт запроса не соответствует платежу")
    if user.id in {requested.actor_user_id, report.reviewed_by_user_id}:
        raise HTTPException(403, "Исправление подтверждает другой администратор")
    key = "correction-approve:" + body.idempotency_key.strip()
    existing = db.query(ExternalPaymentEvent).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if (existing.kind != "correction_approved" or existing.payment_id != payment.id
                or existing.parent_event_id != requested.id or existing.actor_user_id != user.id
                or existing.expected_version != body.expected_version):
            raise HTTPException(409, "Ключ решения уже использован")
        return {"event_id": existing.id, "status": "corrected", "idempotent": True}
    if db.query(ExternalPaymentEvent).filter_by(
        parent_event_id=requested.id, kind="correction_approved"
    ).first():
        raise HTTPException(409, "Исправление уже подтверждено")
    latest = (db.query(ExternalPaymentReport).filter_by(payment_id=payment.id)
              .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
              .first())
    if (latest.id != report.id or report.status != "recorded"
            or body.expected_version != requested.expected_version + 1):
        raise HTTPException(409, "Сведения изменились после запроса")
    if db.query(MoneyMovement).filter_by(payment_id=payment.id).first():
        raise HTTPException(409, "Есть отдельный денежный факт; нужна финансовая сверка")
    reserve_version(db, payment, body.expected_version)
    event = append_event(
        db, payment=payment, report_id=report.id, kind="correction_approved",
        idempotency_key=key, expected_version=body.expected_version,
        actor_user_id=user.id, parent_event_id=requested.id,
        reason_code=requested.reason_code,
    )
    payment.status = "pending"
    obligation = db.get(PaymentObligation, payment.obligation_id) if payment.obligation_id else None
    if obligation and obligation.status == "satisfied":
        obligation.status = "pending"
        obligation.satisfied_at = None
    booking = db.get(Booking, payment.booking_id)
    if booking:
        booking.payout_blocked = True
        booking.payout_block_reason = "external_payment_correction"
    audit(db, actor_user_id=user.id, action="payment.external_correction_approved",
          entity_type="payment", entity_id=payment.id,
          payload={"request_event_id": requested.id, "approval_event_id": event.id,
                   "report_id": report.id, "reason_code": requested.reason_code})
    db.commit()
    return {"event_id": event.id, "status": "corrected", "payment_status": "pending",
            "reliable_money_fact": False, "evidence_version": body.expected_version + 1}


@router.post("/payment-reminders/run")
def run_payment_reminders(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    totp: str | None = None,
):
    admin_sensitive_limiter.check(client_key(request, "admin-payment-reminders"))
    require_admin_2fa(user, totp, request)
    result = enqueue_payment_reminders(db)
    audit(
        db,
        actor_user_id=user.id,
        action="payment.reminders_enqueued",
        entity_type="payment_scheduler",
        entity_id="due-overdue",
        payload=result,
    )
    db.commit()
    return result


@router.get("/metrics")
def pilot_metrics(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"periods": {"7": _period_metrics(db, 7), "30": _period_metrics(db, 30)}}


@router.post("/totp/enable")
def enable_admin_totp_deprecated():
    raise HTTPException(410, "Используйте /auth/admin-totp/challenge и /auth/admin-totp/confirm")


@router.get("/audit")
def list_audit(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return {
        "items": [
            {
                "id": r.id,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.delete("/audit/{audit_id}")
def delete_audit(audit_id: str, _: User = Depends(require_admin)):
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Журнал неизменяемый")


@router.post("/email-outbox/retry")
def retry_email_outbox(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """E21: retry failed/pending email without duplicating already-sent keys."""
    from booker_api.notifications.outbox import retry_pending_outbox

    return retry_pending_outbox(db, actor_user_id=user.id)
