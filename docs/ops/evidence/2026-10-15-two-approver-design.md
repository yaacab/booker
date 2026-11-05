# Two-approver staff recovery — design + tests (OFF)

**Level:** LOCAL  
**Feature flag:** `BOOKER_TWO_APPROVER_RECOVERY_ENABLED` default **false**  
**SMTP / S06 delivery:** still **BLOCKED** (no real SMTP)

## Contract

| Case | Behavior |
| --- | --- |
| Sole platform admin | Offline kit recovery still allowed (unchanged) |
| Multi admin + flag OFF | HTTP `/auth/admin-totp/recover` → **403** |
| Multi admin + flag ON, no second approver | Gate `approver_missing` → deny |
| Same user as approver | `approver_same_as_subject` → deny |
| Approver without TOTP | `approver_totp_required` → deny |
| Flag ON + distinct approver + TOTP | Still `procedure_not_armed` — execution disarmed until owner GO |

## Code

- `apps/api/booker_api/two_approver_recovery.py`
- `apps/api/booker_api/config.py` — `two_approver_recovery_enabled`
- `apps/api/booker_api/routers/identity.py` — uses evaluate gate
- `apps/api/tests/test_two_approver_recovery.py`

## Tests

`pytest tests/test_two_approver_recovery.py` + multi-admin staff recovery + new IDOR cases → PASS.

## Owner decision needed

Item **3** in approval queue: enable two-approver policy + arm procedure (and SMTP for notices). Until then flag stays off; no score claim for S06.
