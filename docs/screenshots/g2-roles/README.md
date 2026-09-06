# G2 — кабинеты ролей (evidence)

Скриншоты кабинетов трёх ролей для G2 pack. Event Studio map flag по умолчанию **OFF**. Платежи — stub.

| Role | Viewport | Route | File |
|------|----------|-------|------|
| customer | 1440×900 | `/cabinet/customer` | `customer-1440.png` |
| customer | 390×844 | `/cabinet/customer` | `customer-390.png` |
| performer (artist) | 1440×900 | `/cabinet/performer` | `performer-1440.png` |
| performer (artist) | 390×844 | `/cabinet/performer` | `performer-390.png` |
| venue | 1440×900 | `/cabinet/venue` | `venue-1440.png` |
| venue | 390×844 | `/cabinet/venue` | `venue-390.png` |

## Capture metadata

- **Date:** 2026-09-06
- **Capture tree SHA:** `ef1f83b7e6d4dbba12e372b9f68b38b09e4f78d2` (branch `agent/w5-screenshots`, base before this docs commit)
- **Demo accounts:** `customer@booker.test` / `artist@booker.test` / `venue@booker.test` (password `password1`)
- **Flags:** Event Studio map v1 default OFF
- **Payments:** stub (no live acquiring)

## How to re-run

From `apps/web` (Playwright стартует API:8000 и Next:3000 при необходимости, `reuseExistingServer: true`):

```bash
cd apps/web
npm run test:e2e -- e2e/g2-screenshots.spec.ts
```

Или из корня репозитория:

```bash
node scripts/capture-g2-role-screenshots.mjs
```

Требуется demo seed (`make seed` / globalSetup e2e) и доступные порты 8000/3000.
