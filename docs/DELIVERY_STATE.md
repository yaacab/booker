# Delivery State

Updated: 2026-09-06 (Agent continue Spec v3 G2)

## Git

- Branch: `feat/master-plan-execution` (integration)
- Docs baseline: `f1a3298`
- Wave 0: `fb24377` (flag OFF, CI master+e2e, calendar≠requests)
- Wave 1: `6adf8c7` (search filters, dual home search, profile SEO)
- PR #14: open — **не merge** без OK владельца
- Prod deploy: **запрещён** в этой сессии

## Правила (зеркало плана)

- G1/G2 **нельзя** при открытых обязательных A+B; `OWNER_BLOCKED` / `ENV_BLOCKED` ≠ done.
- E25 = ожидает G3 (после разрешённого prod deploy).
- Query `?event_studio_map_v1=0|1` = URL-only; глобальный откат = env + rebuild (+ deploy только с OK).
- Stub tests ≠ real PSP; external отдельно; provider webhook/refund ждут live+sandbox.
- CI доказательство = checks на **текущий** SHA/PR; зелёный старый master ≠ готовность.
- Параллель: worktree+ветка от fixed SHA; non-overlapping ownership; отдельные test DB/ports; coordinator интегрирует последовательно; реестр в `DELIVERY_BACKLOG.md`.
- Selective commits; review docs diff; never blind `git add -A`.
- Нет merge/prod без OK владельца.

## Сделано

- Wave 0 VERIFIED (unit + e2e supply-nav + event-studio-map)
- Wave 1 VERIFIED: `/catalog/search` format/travel/budget_max/guests/seating/kind; home dual search; SEO metadata + sitemap profiles; E03 synthetic chip; e2e search-filters

## В работе (локальный WIP — не все закоммичено)

- W2-ONBOARD: CustomerOnboardingWidget + dashboard hook
- W2-AUTOSAVE: EventStudioShell autosave + e2e
- W2-EXT-PAY: deals page UX + `test_external_payment_confirm.py`
- W2 cabinets e2e: cabinets-cross-role.spec.ts

## Следующее

Wave 2 A+B (3 кабинета, deal path, multi-hall, cancel, ext-pay) → Wave 3 discovery → Wave 4 trust → Wave 5 G2 pack. Параллельные слоты — по реестру; без «продолжать?».

## Owner / env blockers (не замена G1/G2)

См. `docs/OWNER_INPUTS.md`. Map provider = C, не блокер W1. Live pay / SMS = C.
