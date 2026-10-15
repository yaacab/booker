"""Two-approver staff TOTP recovery — design gate (OFF by default).

Multi-admin self-recovery with offline codes stays denied unless the owner
enables BOOKER_TWO_APPROVER_RECOVERY_ENABLED *and* a second live approver
session completes the procedure. Until policy GO, this module only enforces
fail-closed denial and documents the intended contract for tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import User


@dataclass(frozen=True)
class TwoApproverDecision:
    allowed: bool
    code: str
    detail: str


def two_approver_feature_enabled() -> bool:
    return bool(getattr(settings, "two_approver_recovery_enabled", False))


def count_platform_admins(db: Session) -> int:
    return db.query(User).filter(User.is_platform_admin.is_(True)).count()


def evaluate_staff_totp_recovery(
    db: Session,
    *,
    subject: User,
    approver_user_id: str | None = None,
    approver_totp_ok: bool = False,
) -> TwoApproverDecision:
    """Fail-closed gate for /auth/admin-totp/recover.

    Sole admin / support operator: caller handles offline-code path separately
    (this function is only consulted for multi-admin platform admins).
    """
    if not subject.is_platform_admin:
        return TwoApproverDecision(True, "not_platform_admin", "operator path uses offline kit")

    admin_count = count_platform_admins(db)
    if admin_count <= 1:
        return TwoApproverDecision(True, "sole_admin", "offline kit permitted for sole admin")

    # Multi-admin: never allow self-recovery without the approved procedure.
    if not two_approver_feature_enabled():
        return TwoApproverDecision(
            False,
            "two_approver_disabled",
            "multi-admin recovery blocked until owner enables two-approver policy",
        )

    # Feature flag on: still require a distinct second approver with fresh TOTP.
    if not approver_user_id:
        return TwoApproverDecision(
            False,
            "approver_missing",
            "second authorized admin session required",
        )
    if approver_user_id == subject.id:
        return TwoApproverDecision(
            False,
            "approver_same_as_subject",
            "subject cannot approve own recovery",
        )
    approver = db.get(User, approver_user_id)
    if not approver or not approver.is_platform_admin or not approver.totp_enabled:
        return TwoApproverDecision(
            False,
            "approver_not_admin",
            "approver must be a live platform admin with TOTP",
        )
    if not approver_totp_ok:
        return TwoApproverDecision(
            False,
            "approver_totp_required",
            "approver TOTP step-up required",
        )
    # Even with flag+approver proofs, execution endpoints are not wired until
    # owner policy GO. Keep fail-closed at the final gate.
    return TwoApproverDecision(
        False,
        "procedure_not_armed",
        "two-approver proofs accepted in design only; execution disarmed until GO",
    )
