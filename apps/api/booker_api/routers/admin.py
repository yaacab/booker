from fastapi import APIRouter, Depends, HTTPException, status
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
from booker_api.schemas import DisputeIn, RefundIn, VerifyIn
from booker_api.security import audit, current_user, require_admin, require_admin_2fa

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/verifications")
def list_verifications(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Verification).filter(Verification.status == "queued").all()
    pending_artists = db.query(Artist).filter(Artist.verified_status == "pending").all()
    return {
        "queue": [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id} for r in rows],
        "artists": [{"id": a.id, "name": a.name, "status": a.verified_status} for a in pending_artists],
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
