from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import (
    Artist,
    AuditLog,
    Booking,
    Dispute,
    Payment,
    User,
    Venue,
    Verification,
)
from booker_api.routers.deals import _transition
from booker_api.schemas import DisputeIn, RefundIn, TotpEnableIn, VerifyIn
from booker_api.security import audit, current_user, now, require_admin, require_admin_2fa

router = APIRouter(prefix="/admin", tags=["admin"])

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
        db.query(func.count(func.distinct(AuditLog.entity_id)))
        .filter(
            AuditLog.created_at >= since,
            AuditLog.action == "client.event",
            AuditLog.entity_id != "",
        )
        .scalar()
        or 0
    )
    by_event = {
        event: count
        for event, count in db.query(AuditLog.entity_id, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since, AuditLog.action == "client.event")
        .group_by(AuditLog.entity_id)
        .all()
    }
    return {"count": base.count(), "unique_entities": unique, "by_event": by_event}


def _period_metrics(db: Session, days: int) -> dict:
    since = now() - timedelta(days=days)
    metrics = {action: _action_metrics(db, since, action) for action in PILOT_ACTIONS if action != "client.event"}
    metrics["client.event"] = _client_event_metrics(db, since)
    metrics["payment"] = _payment_metrics(db, since)
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
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    if booking.status in {"Confirmed", "InProgress"}:
        _transition(booking, "Dispute")
    dispute = Dispute(booking_id=booking_id, category=body.category, body=body.notes)
    db.add(dispute)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.opened",
        entity_type="dispute",
        entity_id=dispute.id,
        payload={"note": "AI не выносит решений по спорам"},
    )
    db.commit()
    db.refresh(dispute)
    return {"id": dispute.id, "status": dispute.status, "ai_decides": False}


@router.post("/refunds")
def refund(
    body: RefundIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_admin_2fa(user, body.totp)
    if body.approver_user_id == user.id:
        raise HTTPException(403, "Возврат требует второго администратора")
    approver = db.get(User, body.approver_user_id)
    if not approver or not approver.is_platform_admin:
        raise HTTPException(403, "Подтверждающий должен быть администратором")
    payment = db.get(Payment, body.payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    payment.status = "refunded"
    audit(
        db,
        actor_user_id=user.id,
        action="payment.refunded",
        entity_type="payment",
        entity_id=payment.id,
        payload={"approver_user_id": approver.id, "reason": body.reason},
    )
    db.commit()
    return {"id": payment.id, "status": payment.status}


@router.get("/metrics")
def pilot_metrics(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"periods": {"7": _period_metrics(db, 7), "30": _period_metrics(db, 30)}}


@router.post("/totp/enable")
def enable_admin_totp(
    body: TotpEnableIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только администратор платформы")
    if user.totp_enabled:
        raise HTTPException(400, "Второй фактор уже включён")
    user.totp_secret = body.secret.strip()
    user.totp_enabled = True
    audit(
        db,
        actor_user_id=user.id,
        action="admin.totp_enabled",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    return {"totp_enabled": True}


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
