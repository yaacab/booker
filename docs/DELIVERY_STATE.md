# Delivery State

Updated: 2026-09-06 (Agent continue Spec v3 G2)

## Git

- Branch: `feat/master-plan-execution` (integration)
- HEAD (pre-commit WIP): `4bf519a` + share/claim/support/outbox
- Docs baseline: `f1a3298`
- Wave 0: `fb24377` VERIFIED (flag OFF, CI master+e2e, calendar≠requests)
- Wave 1: `6adf8c7` VERIFIED
- Wave 2 (partial): `e578301` onboarding/autosave/ext-pay; `449e7e8` multi-hall E10; cancel E11 covered by `test_replacement.py`
- Wave 3: fav `8715009`; briefs `4bf519a`; share/compare (this commit)
- Wave 4: reviews `51214da`; claim/support/outbox (this commit)
- PR #14: open — **не merge** без OK владельца
- Prod deploy: **запрещён**

## Правила (зеркало плана)

- G1/G2 **нельзя** при открытых обязательных A+B; `OWNER_BLOCKED` / `ENV_BLOCKED` ≠ done.
- E25 = ожидает G3.
- Query flag = URL-only; глобальный откат = env + rebuild.
- Stub tests ≠ real PSP.
- CI = checks на текущий SHA/PR.
- Параллель: worktree + non-overlapping; coord sequential integrate; selective commits; never blind `git add -A`.

## Сделано

- Wave 0–1 VERIFIED
- W3-FAV, W3-BRIEF, W3-COMPARE, W3-SHARE (E22 revoke)
- W4-REVIEW, W4-CLAIM (no auto-own), W4-SUPPORT, W4-NOTIF outbox retry (E21)
- W2-MULTI-HALL, W2-CANCEL (api), W2-EXT-PAY (stub≠PSP)

## Открыто (A+B)

- W2 cabinets depth (performer/venue scenarios beyond shells)
- W2-DEAL-PATH e2e polish E07–E09
- W3-SAVED, W3-PROMO
- W4-MSG-HUB
- W5 authz/e2e/a11y/backup/manifest; E25 = G3

## Owner / env blockers (не замена G1/G2)

См. `docs/OWNER_INPUTS.md`. C-LIVE / C-MAP / C-SMS.
