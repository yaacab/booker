"""Server-authoritative readiness of required event positions."""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from booker_api.composition import requirement_payload
from booker_api.models import (
    Booking,
    Event,
    EventTeamRequirement,
    Offer,
    OfferVersion,
    Payment,
    PaymentObligation,
    PaymentPlan,
    Request,
)
from booker_api.payment_scheduler import KINDS, obligation_payload, version_payment_terms

READY_BOOKING_STATUSES = frozenset({"Confirmed", "InProgress", "Completed"})
INACTIVE_REQUEST_STATUSES = frozenset({"Cancelled", "Declined", "Expired"})


def calculate_event_readiness(
    requirements: Iterable[dict[str, Any]],
    requests: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate readiness from server facts without mutating Event status."""
    requests_by_requirement: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for request in requests:
        requirement_id = request.get("requirement_id")
        if requirement_id:
            requests_by_requirement[str(requirement_id)].append(request)

    required_total = 0
    ready_total = 0
    positions: list[dict[str, Any]] = []
    for requirement in requirements:
        if not bool(requirement.get("required", True)):
            continue
        requirement_id = str(requirement.get("id") or "")
        quantity = max(1, int(requirement.get("qty") or 1))
        required_total += quantity
        linked = requests_by_requirement.get(requirement_id, [])
        active = [
            request
            for request in linked
            if request.get("status") not in INACTIVE_REQUEST_STATUSES
        ]
        ready = sum(
            1
            for request in active
            if request.get("booking_status") in READY_BOOKING_STATUSES
        )
        ready = min(quantity, ready)
        ready_total += ready
        missing = quantity - ready
        if missing == 0:
            blocker = None
        elif len(active) < quantity:
            blocker = "no_request"
        elif any(not request.get("quote_id") for request in active):
            blocker = "no_offer"
        elif any(not request.get("booking_id") for request in active):
            blocker = "no_booking"
        else:
            blocker = "not_confirmed"
        positions.append(
            {
                "requirement_id": requirement_id,
                "category_code": requirement.get("category_code"),
                "role_label": requirement.get("role_label") or requirement.get("category_code"),
                "required": quantity,
                "ready": ready,
                "missing": missing,
                "blocker": blocker,
            }
        )

    missing_total = required_total - ready_total
    state = "empty" if required_total == 0 else ("ready" if missing_total == 0 else "incomplete")
    return {
        "state": state,
        "required_total": required_total,
        "ready_total": ready_total,
        "missing_total": missing_total,
        "positions": positions,
    }


def build_event_readiness(db: Session, event: Event, *, lock: bool = False) -> dict[str, Any]:
    requirement_query = db.query(EventTeamRequirement).filter(
        EventTeamRequirement.event_id == event.id
    ).order_by(EventTeamRequirement.id.asc())
    request_query = db.query(Request).filter(Request.event_id == event.id).order_by(Request.id.asc())
    if lock:
        requirement_query = requirement_query.with_for_update()
        request_query = request_query.with_for_update()
    requirements = [requirement_payload(row) for row in requirement_query.all()]
    requests: list[dict[str, Any]] = []
    payment_blockers: list[dict[str, Any]] = []
    for request in request_query.all():
        offer_query = db.query(Offer).filter(Offer.request_id == request.id).order_by(Offer.id.asc())
        if lock:
            offer_query = offer_query.with_for_update()
        offer = offer_query.one_or_none()
        booking = None
        if offer:
            booking_query = db.query(Booking).filter(Booking.offer_id == offer.id).order_by(Booking.id.asc())
            if lock:
                booking_query = booking_query.with_for_update()
            booking = booking_query.one_or_none()
        requests.append(
            {
                "id": request.id,
                "requirement_id": request.requirement_id,
                "status": request.status,
                "quote_id": offer.active_version_id if offer else None,
                "booking_id": booking.id if booking else None,
                "booking_status": booking.status if booking else None,
            }
        )
        if booking and booking.status in READY_BOOKING_STATUSES:
            external_unverified = db.query(Payment.id).filter(
                Payment.booking_id == booking.id,
                Payment.provider == "external",
                Payment.status == "external_recorded",
            ).first() is not None
            if external_unverified or (booking.payout_blocked and booking.payout_block_reason in {
                "legacy_external_unverified", "external_payment_correction"
            }):
                payment_blockers.append({
                    "booking_id": booking.id,
                    "obligation": {"kind": "external_review", "effective_state": "review_required",
                                   "blocks_check_in": True},
                })
            version_id = booking.accepted_offer_version_id
            version = db.get(OfferVersion, version_id) if version_id else None
            plan = (
                db.query(PaymentPlan).filter(PaymentPlan.offer_version_id == version_id).one_or_none()
                if version_id
                else None
            )
            terms = version_payment_terms(version) if version else {}
            if not version or not all(kind in terms for kind in KINDS) or not plan:
                payment_blockers.append(
                    {
                        "booking_id": booking.id,
                        "obligation": {
                            "kind": "schedule_review",
                            "effective_state": "review_required",
                            "blocks_check_in": True,
                        },
                    }
                )
            elif plan:
                obligations_query = db.query(PaymentObligation).filter(
                    PaymentObligation.plan_id == plan.id
                ).order_by(PaymentObligation.id.asc())
                if lock:
                    obligations_query = obligations_query.with_for_update()
                for obligation in obligations_query.all():
                    payload = obligation_payload(obligation)
                    if payload["blocks_check_in"]:
                        payment_blockers.append(
                            {
                                "booking_id": booking.id,
                                "obligation": payload,
                            }
                        )
    readiness = calculate_event_readiness(requirements, requests)
    readiness["payment_blockers"] = payment_blockers
    if readiness["state"] == "ready" and payment_blockers:
        readiness["state"] = "incomplete"
    return readiness
