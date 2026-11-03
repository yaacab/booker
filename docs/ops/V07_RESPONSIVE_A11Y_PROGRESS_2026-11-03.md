# V07 — адаптив / a11y / скорость (локальный агентский объём закрыт → BLOCKED)

**Дата:** 2026-11-03  
**Статус задачи:** BLOCKED (`OWN-MOTION-ACK`)  
**Уровень:** локально  
**Приёмка среза:** `responsive-viewports.spec.ts` — **28 passed**; Lighthouse search@390 perf **95** / a11y **100** (без 3G throttle)

## Уже есть

| Доказательство | Что закрывает |
|---|---|
| `e2e/cabinet-a11y.spec.ts` | landmarks, skip links, Tab, reduced-motion, 390×844 × 3 роли |
| `e2e/responsive-viewports.spec.ts` | viewports + keyboard chains (search→profile→cabinet, requests→deal) + deal/events |
| search labels `htmlFor`/`id` | фокус city / keyboard Найти |
| `V07_LOCAL_PERF_SMOKE_2026-11-03.json` | DCL/FCP smoke |
| `V07_LIGHTHOUSE_LOCAL_SUMMARY_2026-11-03.json` | search perf95/a11y100; home perf88/a11y100 @390 |
| contrast + footer aria | catalog meta/price; footer tagline; label match |
| `@media (max-width: 380px)` | одноколоночный searchbar |

## Ещё нужно для DONE

- Motion fallback после D05 / `OWN-MOTION-ACK` — **блокер владельца**.
- Staging browser E2E — V08.
- Опционально: Lighthouse simulated throttling / HAR на staging supply.

## Запуск

```bash
cd apps/web
./node_modules/.bin/playwright test e2e/responsive-viewports.spec.ts e2e/cabinet-a11y.spec.ts --reporter=line
```
