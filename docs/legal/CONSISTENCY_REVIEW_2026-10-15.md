# Legal consistency pack — review (no publish)

**Date:** 2026-10-15  
**Level:** draft consistency only — **not** lawyer sign-off, **not** publication  
**Pack version string in README:** `2026-10-01-draft`

## Cross-file consistency

| Topic | Sources | Status |
| --- | --- | --- |
| Operator form | `OPERATOR.md`, `OWNER_INPUTS.md`, `OFFER_DRAFT.md` | Placeholders; НПД noted but operator form undecided |
| Public domain | `CONTRACT.md`, offer/privacy | Canon **bukergo.ru**; aliases redirect |
| Support hours | `OPERATOR.md`, `SLA.md`, offer drafts | 10:00–22:00 МСК — duty email still missing |
| Refunds / four-eyes | `DISPUTES_REFUNDS_DRAFT.md`, admin refund API | Aligns with two-admin approve; live partner unproven |
| Payments | `PAYMENTS_SHORTLIST.md`, stub provider | Fail-closed; partner term sheet missing |
| Consent version | README vs API/web constant | **Known blocker:** code may still show `2026-08-18-draft` — sync before publish |
| Hosting 152-ФЗ | `HOSTING_152FZ.md` | RF region required; staging proposal matches |
| Cookies / privacy | drafts | Draft only; no publication |

## Owner checklist before lawyer / publish

Copy from `OWNER_INPUTS.md` P0 — all still open except verbal НПД/YuKassa note:

- [ ] Operator legal form + ИНН/ОГРН + DPO contacts in `OPERATOR.md`
- [ ] ICP: B2B only vs B2C (ЗоЗПП impact)
- [ ] Money flow matrix (advance/balance/commission/refund/payout)
- [ ] Pilot commercial rate (not a range in live docs)
- [ ] YuKassa product fitness letter for multi-supplier
- [ ] РКН notification fact
- [ ] Retention schedule by category
- [ ] Duty email + holiday calendar (support)
- [ ] Sync `legal_pack_version` in API/web to pack revision after lawyer edits

## Explicit non-actions

- No publish of `/legal/*` as binding
- No flip of `BOOKER_LEGAL_PUBLICATION_APPROVED`
- No live acquiring
- Scores / M06 remain open until lawyer+operator GO
