# Owner unblock matrix — final (2026-10-15)

Scores remain **FULL 59 / MVP 56 / Design 15** until criteria pass.

Integration chain (no merge without owner): **PR #20 → PR #22 → PR #23**.

| # | Contour | Decision needed | After GO — agent executes | Blocked without GO |
| --- | --- | --- | --- | --- |
| 1 | **Infrastructure C** (priority) | Purchase/create isolated RF VPS ≠ prod `5.45.112.180`; share SSH | `STAGING_PROVISION_PLAYBOOK.md`: docker, secrets under `/etc/booker-staging`, TLS, seed, C01–C10, backup, evidence → T10/T12 eligible | Staging scores, PG restore RTO |
| 2 | **SMTP** | Test SMTP host + From + mailbox | Wire security notices; prove recovery email LOCAL/staging | S06 mail delivery |
| 3 | **Two-approver** | Approve procedure; then allow arming | Keep flag OFF until second GO to arm `procedure_not_armed` | Multi-admin recovery path |
| 4 | **D02 / motion** | APPROVE / REJECT / REVISE on packet | Integrate tokens/motion only on APPROVE (#23) | Design score |
| 5 | **Legal M06** | Lawyer + filled `OPERATOR.md` | Sync pack version; publication flags | Live legal pages |
| 6 | **Payment partner** | Term sheet / sandbox model | Sandbox only; stub stays until partner GO | Live acquiring |
| 7 | **Operator duty** | Pavel email + channel + backup | Fill `SUPPORT_DUTY_RUNBOOK.md`; SLA claim | Pilot ops |

## Explicit non-actions until GO

- No production SSH/DNS/deploy  
- No live payments / real users  
- No VPS purchase by agent  
- No score inflation  

## Ready artifacts

- Host proposal: `2026-10-15-staging-host-proposal.md`  
- Provision playbook: `docs/ops/STAGING_PROVISION_PLAYBOOK.md`  
- Two-approver design: `2026-10-15-two-approver-design.md`  
- D02 packet: `docs/design/D02_MOTION_APPROVAL_PACKET.md` (#23)  
- Legal: `docs/legal/CONSISTENCY_REVIEW_2026-10-15.md`, `OWNER_PUBLISH_CHECKLIST.md`  
- Approval packet: `2026-10-15-owner-approval-packet.md`  
