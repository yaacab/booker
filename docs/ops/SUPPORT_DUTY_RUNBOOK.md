# Support duty runbook — prep (no real users)

**Status:** LOCAL draft for Stage F / pilot ops  
**Do not** create real operator accounts or email real people from this doc.

## Roles (placeholders until owner fills)

| Role | Name | Email | Channel |
| --- | --- | --- | --- |
| Primary duty | Pavel (named) | **[OWNER: email]** | **[OWNER: Telegram/phone]** |
| Backup duty | **[OWNER]** | **[OWNER]** | **[OWNER]** |
| Platform admin (two-approver) | **[OWNER]** | — | recovery only |

## Window

- Public SLA text: daily 10:00–22:00 Europe/Moscow (`docs/ops/SLA.md`)
- Do **not** publish SLA promise until email + channel + holiday calendar confirmed
- Holiday exceptions: **[OWNER calendar]**

## Daily checklist (synthetic / staging only)

1. Confirm API `/health` and support queue page load on staging (after Infrastructure GO).
2. Confirm overnight escalation cron dry-run log without PII dump.
3. Grant/revoke operator flag only via admin + TOTP; never share recovery codes in chat.
4. On shift handoff: open tickets count, P0 categories (`event_day_no_show`, `paid_not_confirmed`), no plaintext secrets in notes.

## Grant / revoke operator (LOCAL verified path)

- Tests: `test_support_operator_role.py`, support security suite
- Production grant requires verified mailbox + TOTP policy — see identity admin promote flow
- This runbook does **not** authorize creating pilot users

## Escalation

1. Ticket overdue past SLA target → internal notice (SMTP still BLOCKED until owner GO)
2. Payment / refund dispute → two-admin refund path (existing); no self-approve
3. Security / TOTP loss with multi-admin → two-approver packet (flag OFF until policy GO)

## Explicit non-actions

- No real customer/supplier accounts from agent
- No SMTP blast
- No claim that Stage F / pilot ops is complete
