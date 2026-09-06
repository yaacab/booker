# Delivery State

Updated: 2026-09-06 (W5-EVIDENCE — E01–E24 table on candidate SHA)

## Git

- Branch: `feat/master-plan-execution` (integration); evidence worktree `agent/w5-evidence`
- HEAD (candidate for evidence): `ef1f83b`
- Ahead of origin: local; no push required this turn
- PR #14: OPEN — **не merge** без OK владельца
- Prod deploy: **запрещён**

## Wave status

| Wave | Status | Notes |
| ---- | ------ | ----- |
| 0 | VERIFIED | flag OFF, CI master+e2e, calendar≠requests (`fb24377`) |
| 1 | VERIFIED | search/SEO/home (`6adf8c7`) |
| 2 | PARTIAL | multi-hall/cancel/ext-pay + cab perf/venue; deal-path e2e polish open (E07–E09 PARTIAL) |
| 3 | MOSTLY | fav/briefs/share/compare/saved/promo on SHA (`4e262ab`/`c052b61`/wire) |
| 4 | MOSTLY | reviews/claim/support/outbox/msg hub (`15d5880`) |
| 5 | PARTIAL | E01–E24 evidence table filled (`docs/E01_E24_EVIDENCE.md`); RELEASE_MANIFEST checkboxes still open; screenshots ×3 roles incomplete |
| E25 | ожидает G3 | — |

## G2 evidence snapshot (`ef1f83b`)

- Table: `docs/E01_E24_EVIDENCE.md` — **15 PASS / 9 PARTIAL / E25 G3**
- Backup: `docs/ops/RESTORE_DRILL_LOG.md` PASS 2026-09-06 + `apps/api/tests/test_backup_restore.py`
- A11y: `apps/web/e2e/cabinet-a11y.spec.ts` (E24 PARTIAL — not full SR + 3-role shots)
- **G2 не закрыт**

## Owner / env blockers (≠ done)

- C-LIVE / C-MAP / C-SMS — `docs/OWNER_INPUTS.md`
- Stub payments ≠ real PSP
- E25 requires owner OK for prod

## Next (no «продолжать?»)

1. Deal-path critical e2e (E07–E09) + expand CI e2e list
2. Screenshots 1440/390 × 3 roles
3. Finalize RELEASE_MANIFEST checkboxes (coord); G2 only when A+B closed
