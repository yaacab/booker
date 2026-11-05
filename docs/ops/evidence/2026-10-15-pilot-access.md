# Stage E — Pilot access readiness (no real users)

Date: 2026-10-15  
Candidate: `bb61e998`  
Classification: READ-ONLY / SAFE LOCAL docs — **no real pilot accounts granted**

## Existing roles (code + seed)

| Role | Source | Notes |
|---|---|---|
| Customer / artist / venue demo | `booker_api/seed.py` (`BOOKER_ALLOW_DEMO_SEED=1`) | Local/test only; forbidden in production seed path |
| Platform admin | `admin@booker.test` in demo seed | TOTP step-up required for admin support actions |
| Support operator | `is_support_operator` | Grant/revoke via `/admin/support/operators`; email verified + TOTP required; org membership forbidden |

## Minimal rights (verified locally earlier + this run)

- Operator ACL limited to `/me`, logout, `/admin/support/tickets*` (see SUPPORT_OPERATOR_QUEUE doc).
- Authz regressions PASS in Stage C suite.
- Grant/revoke invalidates prior bearer sessions (documented + prior Playwright).

## Duty operator

- Named duty owner (Павел) exists in ops notes; **registered email still unknown** → real duty routing **not** enabled.
- External signal channel / backup shift: open (PROJECT_PROGRESS S06/O06).

## Error handling

- Support queue CAS (`If-Match` / state_version) → 409 refresh path present.
- Stub payments fail-closed for live without partner gate.

## Limited pilot rules (proposed; not activated)

1. Only non-prod / staging after Stage B unblock.
2. Demo seed credentials never on production.
3. No live acquiring; `BOOKER_PAYMENT_PROVIDER=stub`.
4. Operator grant only after verified email + TOTP enrollment.
5. Explicit owner GO required before inviting real participants.
6. Stop criteria: data leak, double-book failure, payment live accident, restore failure.

## Status

**IMPLEMENTED** locally / documented. **Not ACCEPTED for real pilot** until staging + owner GO.
