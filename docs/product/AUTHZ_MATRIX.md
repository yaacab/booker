# Матрица авторизации (object auth)

Источник: CONTRACT v2, RBAC PR #4. Тесты: `test_idor_events.py`, `test_workspace.py`, `test_cabinet.py`.

## Роли workspace

| role | read org data | write (offers, services) | confirm offer | admin platform |
|------|---------------|--------------------------|---------------|----------------|
| owner | ✓ | ✓ | ✓ | — |
| admin | ✓ | ✓ | ✓ | — |
| manager | ✓ | ✓ | ✓* | — |
| viewer | ✓ | — | — | — |
| platform_admin | ✓ all | ✓ all | ✓ | ✓ |

\* `can_confirm_offer` может быть снят на уровне TeamMember.

## Объекты и проверки

| Объект | Операция | Кто может | Guard |
|--------|----------|-----------|-------|
| Event | GET | member org заказчика | `organization_id` match |
| Event | POST/PUT requirements | writer customer org | `require_org_writer` |
| Request | POST | writer customer org | event belongs to org |
| Request | POST offer | writer supplier org | request targets supplier resource |
| Booking/Deal | GET | customer or supplier org on deal | membership on both sides |
| Service | POST | writer artist/venue org | `organization_id` |
| Hall | POST | writer venue org owns venue | `organization_id` on venue |
| Admin audit/metrics | GET | `is_platform_admin` | `require_admin` |
| Admin refund | POST | admin + optional 2FA | `require_admin_2fa` |
| Payment webhook | POST | HMAC signature | `verify_webhook_signature` |

## Negative tests (обязательные)

- User A не читает Event org B (`test_idor_events`)
- Viewer не создаёт offer/service
- Non-admin не вызывает `/admin/*`
- Invalid webhook signature → 401

## Не реализовано (внешний блокер)

- **ClamAV / внешний AV** — **EXTERNAL_BLOCKED**: нужен prod object storage + sidecar ClamAV; базовая проверка magic bytes — `file_scan.py`

## Реализовано (P0 security)

- Prod 2FA: `BOOKER_REQUIRE_ADMIN_2FA_ENFORCED=1` блокирует admin без TOTP
- Rate limits: см. `booker_api/rate_limit.py`
  - auth (register/login/recover): 20 / 5 min
  - webhook: 120 / min
  - analytics events: 120 / min
  - attachment upload: 30 / 5 min
  - admin TOTP + refund: 10 / 5 min
  - deal-room messages: 60 / min

## Upload (Deal Room)

| Объект | Операция | Кто может | Guard |
|--------|----------|-----------|-------|
| Booking attachment | POST | writer customer/supplier on deal | `scan_upload`, size cap |
