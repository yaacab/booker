# OWNER_INPUTS — данные владельца «Букер»

Единый реестр внешних данных. **Секреты не хранить в git** — только имя переменной и место установки (systemd, GitHub Secrets, vault).

| ID | Значение | Где используется | Обязательно для | Статус |
|----|----------|------------------|-----------------|--------|
| `LEGAL_ENTITY_NAME` | `{{LEGAL_ENTITY_NAME}}` | Оферта, футер, OPERATOR.md | U5, платежи | **pending** |
| `LEGAL_ENTITY_TYPE` | `{{LEGAL_ENTITY_TYPE}}` | Юрдокументы | U5 | **pending** |
| `INN` | `{{INN}}` | Оферта, реквизиты | U5, платежи | **pending** |
| `OGRN_OR_OGRNIP` | `{{OGRN_OR_OGRNIP}}` | Оферта | U5 | **pending** |
| `LEGAL_ADDRESS` | `{{LEGAL_ADDRESS}}` | Оферта, 152-ФЗ | U5 | **pending** |
| `POSTAL_ADDRESS` | `{{POSTAL_ADDRESS}}` | Корреспонденция | U5 | **pending** |
| `OWNER_FULL_NAME` | `{{OWNER_FULL_NAME}}` | OPERATOR.md | U5 | **pending** |
| `SUPPORT_EMAIL` | `{{SUPPORT_EMAIL}}` | UI, legal, уведомления | prod support | **pending** |
| `SUPPORT_PHONE` | `{{SUPPORT_PHONE}}` | UI, legal | prod support | **pending** |
| `SECURITY_EMAIL` | `{{SECURITY_EMAIL}}` | security.txt, инциденты | prod | **pending** |
| `PRIVACY_EMAIL` | `{{PRIVACY_EMAIL}}` | Политика ПДн | U5 | **pending** |
| `PAYMENT_PARTNER` | `{{PAYMENT_PARTNER}}` | `BOOKER_PAYMENT_PROVIDER` | live payments | **pending** |
| `PAYMENT_MERCHANT_ID` | `BOOKER_PAYMENT_MERCHANT_ID` (systemd) | payment adapter | live payments | **pending** |
| `PAYMENT_PUBLIC_KEY` | `BOOKER_PAYMENT_PUBLIC_KEY` (systemd) | payment adapter | live payments | **pending** |
| `PAYMENT_SECRET_KEY` | `BOOKER_PAYMENT_SECRET_KEY` (systemd) | payment adapter | live payments | **pending** |
| `PAYMENT_WEBHOOK_SECRET` | `BOOKER_WEBHOOK_SECRET` (systemd) | webhook verify | live payments | **pending** |
| `SMS_PROVIDER` | `BOOKER_SMS_PROVIDER` | notifications SMS | SMS OTP | **pending** |
| `SMS_API_KEY` | `BOOKER_SMS_API_KEY` (systemd) | notifications SMS | SMS OTP | **pending** |
| `EMAIL_PROVIDER` | `BOOKER_EMAIL_PROVIDER` | notifications email | email | **pending** |
| `EMAIL_API_KEY` | `BOOKER_EMAIL_API_KEY` (systemd) | notifications email | email | **pending** |
| `OBJECT_STORAGE_PROVIDER` | `BOOKER_OBJECT_STORAGE_PROVIDER` | uploads, ClamAV | file upload prod | **pending** |
| `OBJECT_STORAGE_BUCKET` | `BOOKER_OBJECT_STORAGE_BUCKET` | uploads | file upload prod | **pending** |
| `OBJECT_STORAGE_ACCESS_KEY` | `BOOKER_OBJECT_STORAGE_ACCESS_KEY` (systemd) | uploads | file upload prod | **pending** |
| `OBJECT_STORAGE_SECRET_KEY` | `BOOKER_OBJECT_STORAGE_SECRET_KEY` (systemd) | uploads | file upload prod | **pending** |
| `SENTRY_DSN` | `BOOKER_SENTRY_DSN` (systemd) | error tracking | prod observability | **optional** |
| `ANALYTICS_PROVIDER` | `BOOKER_ANALYTICS_PROVIDER` | внешняя аналитика | optional | **optional** |
| `ANALYTICS_KEY` | `BOOKER_ANALYTICS_KEY` (systemd) | внешняя аналитика | optional | **optional** |
| `PRODUCTION_HOST` | `bukergo.ru` (канон) | deploy, CORS | prod | **known** |
| `PRODUCTION_SSH_USER` | `{{PRODUCTION_SSH_USER}}` | deploy-vps.sh | deploy | **pending** |
| `DATABASE_URL` | `BOOKER_DATABASE_URL` (systemd) | API | prod DB | **pending** (SQLite на пилоте) |
| `REDIS_URL` | `BOOKER_REDIS_URL` (systemd) | sessions/rate limit scale | horizontal API | **optional** |
| `DNS_PROVIDER` | `{{DNS_PROVIDER}}` | DOMAINS.md | DNS | **pending** |
| `RKN_REGISTRATION_STATUS` | `{{RKN_REGISTRATION_STATUS}}` | legal gate | U5 | **pending** |
| `LAWYER_APPROVAL_DATE` | `{{LAWYER_APPROVAL_DATE}}` | legal gate U5 | live payments | **pending** |
| `CANCELLATION_POLICY_APPROVAL` | `{{CANCELLATION_POLICY_APPROVAL}}` | legal | U5 | **pending** |
| `PRIVACY_POLICY_APPROVAL` | `{{PRIVACY_POLICY_APPROVAL}}` | legal | U5 | **pending** |
| `PAYMENT_FLOW_APPROVAL` | `{{PAYMENT_FLOW_APPROVAL}}` | legal | live payments | **pending** |
| `AI_PROVIDER` | `BOOKER_AI_PROVIDER` | AI features | AI assist | **optional** |
| `AI_API_KEY` | `BOOKER_AI_API_KEY` (systemd) | AI features | AI assist | **optional** |
| `VENUE_OUTREACH_CONTACT` | `{{VENUE_OUTREACH_CONTACT}}` | перевод open-data площадок на owner calendar | founding supply | **optional** |
| `VENUE_OPEN_IMPORT_NOTES` | см. `docs/ops/VENUE_OPEN_IMPORT.md` | курация `data/moscow_venues_open.json` | каталог Москва | **known** |

## Как заполнить

1. Заполните колонку «Значение» (или передайте Cursor пары `ID=value`).
2. Секреты установите в `/etc/systemd/system/booker-api.service` или GitHub Actions secrets.
3. Юридические поля согласуйте с юристом перед U5.

При отсутствии значения приложение **запускается**, зависимая функция **выключена**, UI сообщает о недоступности.
