# CI secret-source fix + PR chain (2026-10-15)

## Secret-source (was 13 FAIL on run 38680614400)

| Path hash | File | Fix |
| --- | --- | --- |
| `file#76ed074a9305` | `Makefile` | Removed default `booker:booker` URL; require `BOOKER_DATABASE_URL` |
| `file#e87b6298ec40` | `infra/env.staging.example` | `{{STAGING_PG_PASSWORD}}` templates only |
| `file#36f11aa66ac0` | `infra/test_staging_preflight.py` | Synthetic `test-staging-local-only` + file-bound FAKE_FIXTURE; no f-string `{password}` URL literal |

Also: preflight refuses unreplaced `{{…}}` / `REPLACE_WITH_*` so copied examples cannot start staging.

Scanner **not** weakened (no global exclusions). Local: `python3 scripts/check_secret_exposure.py --source` → **OK**.

Delivery SHA: `8c103a3`  
Design SHA (includes merge of delivery): `c414e72`

## PR chain

| PR | Base | Scope |
| --- | --- | --- |
| #20 | `master` | Product candidate `bb61e998` |
| #22 | `codex/booker-integrated-mvp-20261003` (#20) | ~61 delivery files |
| #23 | `cursor/delivery-mvp-acceptance-cbf8` (#22) | **4 design files only** |

No force-push; design merged delivery via merge commit.

## Scores

Unchanged 59 / 56 / 15.
