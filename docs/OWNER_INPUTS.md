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
