# V07 — адаптив / a11y / скорость (прогресс, не DONE)

**Дата:** 2026-11-03  
**Статус задачи:** IN PROGRESS  
**Уровень:** локально  
**Приёмка среза:** `responsive-viewports.spec.ts` — **28 passed** (2026-11-03; +keyboard cabinet request→deal)

## Уже есть

| Доказательство | Что закрывает |
|---|---|
| `e2e/cabinet-a11y.spec.ts` | landmarks, skip links, Tab, reduced-motion, 390×844 × 3 роли |
| `e2e/responsive-viewports.spec.ts` | 320/390/768/1440: home + search + customer/artist/venue cabinets; deal room @390; events/new @320 |
| search labels `htmlFor`/`id` | фокус на `#catalog-search-city`, keyboard path city→Найти→artist profile |
| local load timing smoke @390 | shell <12s + `domContentLoadedEventEnd` <10s (не Lighthouse LCP) |
| `catalog-reference-v2.css` `@media (max-width: 380px)` | одноколоночный searchbar / grid на узких |

## Ещё нужно для DONE (PROJECT_PROGRESS V07)

- Единый end-to-end keyboard path одной сессией (сейчас два chain-теста: search→profile→cabinet и requests→deal).
- Performance budget (LCP/INP или локальный HAR) — smoke timing не заменяет.
- Fallback / reduced-motion на motion после D05 (motion UNAPPROVED).
- Staging browser E2E — V08.

## Запуск

```bash
cd apps/web
./node_modules/.bin/playwright test e2e/responsive-viewports.spec.ts e2e/cabinet-a11y.spec.ts --reporter=line
```
