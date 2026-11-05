# Owner GO execution — 2026-11-05

Источник команды владельца в чате: **«1-2-3-4-GO»** (staging / git-integration / design ACK / OAuth+SMTP).  
`OWN-PROD-GO`, live payments, legal publish — **не** входят.

## 2) OWN-GIT-INTEGRATION-GO — DONE

| Поле | Значение |
|---|---|
| Действие | Merge PR #28 → `master` |
| PR | https://github.com/yaacab/booker/pull/28 |
| Merge commit | `3f52b582309fe95d23a6b402870c7739f319270b` |
| Время | 2026-11-05T06:42:58Z |
| CI на кандидате | 5/5 SUCCESS на `32ec8fc` |
| Production deploy | **не** выполнялся |

## 3) OWN-DESIGN-ACK — DONE (статика DRAFT)

Утверждён **текущий DRAFT wireframe/IA pack** как статичный канон ключевых путей до pixel Figma:

- `docs/design/V04_KEY_PATH_STATE_MATRIX_DRAFT_2026-11-03.md`
- `docs/design/V04_WIREFRAME_HOME_DEAL_STATES_DRAFT_2026-11-03.md`
- `docs/design/V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_DRAFT_2026-11-03.md`
- `docs/design/ARTIST_VNEXT_STORYBOARD_DRAFT_2026-11-03.md`

Не входит в этот ACK:

- `OWN-MOTION-ACK` / motion «Рамка слота»
- Pixel Figma pack → всё ещё нужен для **V04 DONE**
- Перенос в `apps/web` (V05) — после V04

## 1) OWN-STAGING-GO — DONE (разрешение); хост ещё нет

Владелец разрешил отдельный staging (не production).

| Проверка 2026-11-05 | Результат |
|---|---|
| `dig staging.bukergo.ru` | NXDOMAIN / пусто |
| Prod `bukergo.ru` | `5.45.112.180` HTTP 200 |
| Отдельный staging VPS | **не создан** |

**Запрет:** не вешать `staging.bukergo.ru` на prod IP `5.45.112.180`.

Чтобы закрыть `REL-STAGING-HOST`, владельцу нужно прислать:

1. IP отдельного VPS (РФ)
2. SSH user + ключ для агента
3. Подтверждение DNS A `staging.bukergo.ru` → **этот** IP

Дальше агент по `docs/ops/STAGING_PROVISION_PLAYBOOK.md`.

## 4) OWN-OAUTH-YANDEX-VK / OWN-SMTP — ждут секреты

Разрешение получено, значений секретов нет. Intake: `docs/ops/SECRETS_INTAKE_OAUTH_SMTP_2026-11-05.md`.  
Статусы задач остаются TODO до появления рабочих значений вне Git.
