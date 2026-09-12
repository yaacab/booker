# Prelaunch commercial v1 — журнал реализации и приёмки

OWNER DIRECTIVE 2026-09-12: preparation for commercial launch and monetization.

Статус: **в работе**. Этот документ не подтверждает готовность запуска.
Полный объём — разделы 0–35 задания владельца от 2026-09-12.

## Исходное состояние, 2026-09-12

- `origin/master`, проверенный через fetch: `ca20ac2`.
- База рабочей ветки: `834fb22`; содержит master, действующий lime-дизайн
  и модерацию каталога площадок. Сохраняем эти изменения.
- Ветка: `feat/prelaunch-commercial-v1`; отдельный worktree
  `outputs/prelaunch-commercial-worktree`. Незакоммиченные изменения исходного
  каталога не входят в эту задачу и не переносятся.
- API: FastAPI, SQLAlchemy, Alembic; web: Next 15 / React 19.
- Уже есть: Organization/TeamMember RBAC, EventTeamRequirement, версия оффера
  и quote_id, ack, защищённый hold, Deal Room, договор, payment adapter,
  public briefs/response, favorites/compare/shared shortlist, saved searches,
  отзывы Completed, replacement, in-app/email abstraction, append-only audit.
- Старый DELIVERY_GAP_ANALYSIS датирован 2026-09-06 и ошибочно отмечает часть
  перечисленных реализованных функций отсутствующими. Он не является доказательством.
- Коммерческих plans/subscriptions/billing orders/paid campaigns нет.
  Текущий pricing использует 10% и льготу первой сделки; v3 должен явно
  заменить политику новых офферов и сохранить старые снимки.
- Growth, server matching/compatibility/readiness/budget и Business предстоит
  реализовать; текущие event next steps выводятся на клиенте.
- Публичный профиль артиста пока выдаёт примерное время ответа текстом;
  требуются измеренные факты или неизвестное значение.
- В CI уже есть API, web и критические Playwright на PR; расширить коммерцией.
- Юридический пакет остаётся черновиком; provider boundary допустим,
  реальные платежи/production/DNS/merge запрещены этой задачей.

## Последовательность и критерии доказательства

- [ ] 1–4, 6: Contract v3, catalog, models/migration, providers, fees/entitlements.
- [ ] 5, 8, 22: pricing, кабинеты, admin commercial center.
- [ ] 7, 9–11: promotion ranking/attribution, Growth, Opportunities, EPK.
- [ ] 12–20: matching, compare, compatibility, readiness, budget, collaboration,
  repeat, replacement, Business.
- [ ] 21, 23–28: notifications, analytics, SEO/trust/security, mobile/states/flags.
- [ ] 29–31: API coverage, все именованные E2E desktop/390, CI и build.
- [ ] 32–35: документация, provider handoff, аудит каждого требования и отчёт.

Для каждого пункта нужны конкретные UI/API/DB/auth/audit/tests и состояния
loading/empty/error, где применимо. Наличие страницы или зелёный узкий тест
не подтверждает весь пункт. Все непроверенные требования остаются открытыми.

## Проверки

- Исходный `make test-api PYTHON=/home/art67/booker/.venv/bin/python`:
  не запущен — GNU make отсутствует в PATH. Запущен эквивалент
  `cd apps/api && /home/art67/booker/.venv/bin/python -m pytest -q`;
  результат будет записан после завершения.


## Коммерческое ядро — первый инкремент

Реализованы модели и migration `d9e0f1a2b3c4`, каталог/entitlements, disabled/stub
provider, заказы подписок, проверка webhook/идемпотентность, ручной admin grant,
версионированное изменение тарифов, отмена/выбор тарифа следующего периода,
Contract v3 и fee snapshots с DB immutability guard.
Это не закрывает целиком разделы 1–4/6: UI, promotion lifecycle, recurring
integration acceptance и общая приёмка ещё впереди.

Проверки на исправном Python 3.12.14 в отдельном `.venv`:

- Исходный SHA `834fb22`, извлечённый в `/tmp/booker-prelaunch-baseline`:
  `python -m pytest -q` — **203 passed, 2 skipped** (32.48s).
- Текущая ветка: `cd apps/api && ../../.venv/bin/python -m pytest -q` —
  **228 passed, 2 skipped** (36.68s). Включает 25 новых parametrized API cases
  и upgrade/downgrade с историческим оффером. Два skip относятся к исходному suite.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- Node 24.19.0 / npm 10.9.3 и GNU make подготовлены локально; системная среда
  не изменялась. Старый venv не используется из-за отсутствующего libssl 1.1.
- PostgreSQL runtime и браузерная приёмка этого инкремента пока не проверены.
