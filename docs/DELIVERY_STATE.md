# Delivery State

Updated: 2026-09-06

## Git

- Branch: `feat/master-plan-execution`
- Docs baseline: `f1a3298`
- PR #14: open — **не merge** без OK владельца
- Prod deploy: **запрещён** в этой сессии

## Wave 0 (в работе / локально)

- W0-FLAG: `isEventStudioMapV1` = query → env → **default OFF**; unit `lib/features.test.ts`; deploy env default OFF
- W0-CI: `ci.yml` push/PR на `master` (+`main`); job `e2e-critical` на SHA кандидата
- W0-NAV / W0-CAB-ROUTES: `/cabinet/{performer|venue}/{calendar|requests}`; SiteChrome + SupplyCabinetNav; e2e `supply-nav.spec.ts`

## Следующее

1. Локально: unit + critical e2e → коммит Wave 0
2. Wave 1: search filters, home dual search, SEO
3. Без merge/prod; E25 = G3

## Owner / env blockers (не замена G1/G2)

См. `docs/OWNER_INPUTS.md`: PAYMENT_PARTNER, MAP_*, EMAIL/SMS, legal entity, LAWYER_APPROVAL.
