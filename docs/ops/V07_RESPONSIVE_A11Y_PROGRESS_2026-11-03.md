# V07 — адаптив / a11y / скорость (IN PROGRESS)

**Дата:** 2026-11-03  
**Статус задачи:** IN PROGRESS (формальный design DONE всё ещё связан с `OWN-MOTION-ACK`/`D06`)  
**Уровень:** локально  
**Приёмка среза:** unified keyboard chain PASS; Lighthouse search@390 perf **95** / a11y **100** (без 3G throttle)

## Уже есть

| Доказательство | Что закрывает |
|---|---|
| `e2e/cabinet-a11y.spec.ts` | landmarks, skip links, Tab, reduced-motion, 390×844 × 3 роли |
| `e2e/responsive-viewports.spec.ts` | viewports + unified keyboard + login + artist profile @390/1440 + compare @390 + legal/offer @320 |
| search labels `htmlFor`/`id` | фокус city / keyboard Найти |
| local 2026-11-05 | artist/compare/legal overflow suite 7/7 PASS |
| local 2026-11-05b | faq / for-artists / support public @390 — 3/3 PASS |
| local 2026-11-05c | + legal/privacy @390 — 4/4 PASS (venue catalog skipped: published=0) |
| local 2026-11-05d | assemble / briefs / investor venues @390 — 3/3 PASS |
| local 2026-11-05e | performer services / calendar / messages @390 landmark+Tab+overflow |
| local 2026-11-05f | venue halls/requests/calendar + customer messages/favorites + recover + control room @390 PASS |
| `V07_LOCAL_PERF_SMOKE_2026-11-03.json` | DCL/FCP smoke |
| `V07_LIGHTHOUSE_LOCAL_SUMMARY_2026-11-03.json` | search perf95/a11y100; home perf88/a11y100 @390 |
| contrast + footer aria | catalog meta/price; footer tagline; label match |
| `@media (max-width: 380px)` | одноколоночный searchbar |

## Ещё нужно для DONE

- Formal design/motion sign-off (`OWN-MOTION-ACK` / D06) — без этого не ставить V07 DONE в weighted design scale.
- Staging browser E2E — V08.
- Simulated-throttle Lighthouse / HAR на staging (локальный simulate на этом хосте дал interstitial error).

## Запуск

```bash
cd apps/web
./node_modules/.bin/playwright test e2e/responsive-viewports.spec.ts e2e/cabinet-a11y.spec.ts --reporter=line
```
