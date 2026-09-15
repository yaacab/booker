# OWNER_INPUTS — данные владельца «Букер» (Spec v3)

Единый реестр внешних данных. **Секреты не хранить в git** — только имя переменной и место установки (systemd, GitHub Secrets, vault).

| ID | Значение | Для чего | Обязательно | Где настроить | Проверка | Разблокирует | Статус |
|----|----------|----------|-------------|---------------|----------|--------------|--------|
| `LEGAL_ENTITY_NAME` | `{{LEGAL_ENTITY_NAME}}` | Оферта, футер, OPERATOR | U5 | legal/OPERATOR + UI | нет плейсхолдеров | draft off | **pending** |
| `LEGAL_ENTITY_TYPE` | `{{LEGAL_ENTITY_TYPE}}` | Юрдокументы | U5 | legal | — | U5 | **pending** |
| `INN` | `{{INN}}` | Оферта, реквизиты | U5, платежи | legal | — | U5 | **pending** |
| `OGRN_OR_OGRNIP` | `{{OGRN_OR_OGRNIP}}` | Оферта | U5 | legal | — | U5 | **pending** |
| `LEGAL_ADDRESS` | `{{LEGAL_ADDRESS}}` | Оферта, 152-ФЗ | U5 | legal | — | U5 | **pending** |
| `POSTAL_ADDRESS` | `{{POSTAL_ADDRESS}}` | Корреспонденция | U5 | legal | — | U5 | **pending** |
| `OWNER_FULL_NAME` | `{{OWNER_FULL_NAME}}` | OPERATOR | U5 | legal | — | U5 | **pending** |
| `SUPPORT_EMAIL` | `{{SUPPORT_EMAIL}}` | UI, support | prod | systemd/UI | mailto | W4-SUPPORT | **pending** |
| `SUPPORT_PHONE` | `{{SUPPORT_PHONE}}` | UI, legal | prod | UI | — | support | **pending** |
| `SECURITY_EMAIL` | `{{SECURITY_EMAIL}}` | security.txt | prod | systemd | — | security | **pending** |
| `PRIVACY_EMAIL` | `{{PRIVACY_EMAIL}}` | Политика ПДн | U5 | legal | — | U5 | **pending** |
| `PAYMENT_PARTNER` | `{{PAYMENT_PARTNER}}` | выбор адаптера | live | OWNER + code | sandbox | C-LIVE | **pending** |
| `PAYMENT_MERCHANT_ID` | env only | live adapter | live | systemd | — | C-LIVE | **pending** |
| `PAYMENT_PUBLIC_KEY` | env only | live adapter | live | systemd | — | C-LIVE | **pending** |
| `PAYMENT_SECRET_KEY` | env only | live adapter | live | systemd | — | C-LIVE | **pending** |
| `PAYMENT_WEBHOOK_SECRET` | env only | webhook | live | systemd | ≠ default | C-LIVE | **pending** |
| `SMS_PROVIDER` / `SMS_API_KEY` | env | SMS | optional | systemd | — | C-SMS | **pending** |
| `EMAIL_PROVIDER` / `EMAIL_API_KEY` / SMTP | env | email OTP/recover | optional pilot | systemd | test send | W4-NOTIF E21 | **pending** |
| `OBJECT_STORAGE_*` | env | uploads | optional | systemd | upload+restore | W5-BACKUP | **pending** |
| `SENTRY_DSN` | env | errors | optional | systemd | event | observability | **optional** |
| `ANALYTICS_*` | env | внешняя аналитика | optional | systemd | — | — | **optional** |
| `PRODUCTION_HOST` | `bukergo.ru` | deploy/CORS | prod | known | curl | — | **known** |
| `DATABASE_URL` | env | API DB | optional PG | systemd | migrate | PG cutover | **pending** (SQLite) |
| `REDIS_URL` | env | scale | optional | systemd | — | — | **optional** |
| `DNS_PROVIDER` | — | DNS | ops | — | — | — | **pending** |
| `RKN_REGISTRATION_STATUS` | — | 152-ФЗ | U5 | legal | — | U5 | **pending** |
| `LAWYER_APPROVAL_DATE` | — | U5 gate | live | OWNER | date set | C-LIVE | **pending** |
| `CANCELLATION_POLICY_APPROVAL` | — | legal | U5 | legal | — | U5 | **pending** |
| `PRIVACY_POLICY_APPROVAL` | — | legal | U5 | legal | — | U5 | **pending** |
| `PAYMENT_FLOW_APPROVAL` | — | legal | live | legal | — | C-LIVE | **pending** |
| `MAP_PROVIDER` + key | env | карта площадок | optional B | systemd + NEXT_PUBLIC | tiles | C-MAP | **pending** |
| `NEXT_PUBLIC_EVENT_STUDIO_MAP_V1` | `0`/`1` | Map Studio | optional | **rebuild web** | E05 | W0-FLAG | default OFF after W0 |
| `VENUE_OUTREACH_CONTACT` | — | founding supply | optional | ops | — | supply | **optional** |
| `VENUE_OPEN_IMPORT_NOTES` | docs | каталог Москва | known | VENUE_OPEN_IMPORT | — | — | **known** |

## Как заполнить

1. Несекретные значения — в таблицу или `docs/legal/OPERATOR.md`.
2. Секреты — `/etc/booker/booker-api.env` / vault / GitHub Secrets (не git).
3. Юридические поля — с юристом до U5.
4. `OWNER_BLOCKED` в `DELIVERY_BACKLOG.md` ссылается на ID отсюда; независимые задачи продолжаются.

При отсутствии значения приложение **запускается**, зависимая функция **выключена**, UI сообщает о недоступности — не маскировать заглушкой «успех».

## Commercial v3 — дополнительные переменные (2026-09-12)

По директиве владельца коммерческий код готовится заранее; действующие U5 и
инфраструктурные gates сохраняются. Секреты по-прежнему не коммитятся.

- `BOOKER_ENVIRONMENT=production` — безопасный default.
- `BOOKER_COMMERCE_PROVIDER=disabled` — online billing недоступен до adapter.
- `BOOKER_COMMERCE_WEBHOOK_SECRET` — отдельный секрет webhook выбранного партнёра.
- `BOOKER_COMMERCE_ALLOW_STUB=false` — тестовая оплата в production недоступна
  даже при ошибочном включении. Для стенда нужны одновременно dev/test,
  provider=stub, явный opt-in и отдельный ключ длиной от 32 символов.

Точки подключения и acceptance:
[PAYMENT_PROVIDER_HANDOFF.md](integrations/PAYMENT_PROVIDER_HANDOFF.md).
Статус реализации и доказательства: [PRELAUNCH_V1.md](product/PRELAUNCH_V1.md).

Booking checkout также выключен по умолчанию:
`BOOKER_PAYMENT_PROVIDER=disabled`, `BOOKER_PAYMENT_ALLOW_STUB=false`.
Тестовый booking provider требует одновременно dev/test environment, provider=stub
и allow_stub=true; production запрещает stub независимо от opt-in.


### Явный допуск зарегистрированного адаптера

`BOOKER_PAYMENT_LIVE_OPT_IN`, `BOOKER_COMMERCE_LIVE_OPT_IN`,
`BOOKER_PAYMENT_SANDBOX_ACCEPTED` по умолчанию false. Установка true разрешена
только после соответствующего внешнего допуска; сами поля его не доказывают.
Дополнительно нужны ISO-дата LAWYER_APPROVAL_DATE, PAYMENT_FLOW_APPROVAL=approved,
merchant/public/secret keys, секреты webhook ≥32 символов, оба allow_stub=false,
allow_default_webhook_secret=false и require_admin_2fa_enforced=true.
Все названия имеют префикс BOOKER_. Пока нет зарегистрированного адаптера,
никакая комбинация этих значений не включает live. Реестр и точный контракт:
[PAYMENT_PROVIDER_HANDOFF.md](integrations/PAYMENT_PROVIDER_HANDOFF.md).
