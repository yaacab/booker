# Staging package hardened (post-owner A/B/C)

Date: 2026-10-15  
Base SHA before change: `261f76d`  
Owner policy: **A** = local tests OK, not auto-staging scores; **B** = use remote only if proven (not found); **C** = host proposal ready, no purchase.

## Fixes vs prior package

| # | Requirement | Change |
|---|---|---|
| 1 | Fail-closed preflight | `infra/staging_preflight.py` — URL/host/db/user/port/runtime/compose/uploads/payment |
| 2 | No inherited compose ports | Standalone `docker-compose.staging.yml` only (no merge with main compose); config check for 15432, refuse 5432 |
| 3 | No fixed remote passwords in Git | `env.staging.example` placeholders; real secrets via `BOOKER_STAGING_ENV_FILE` outside Git |
| 4 | migrate cannot hit prod via ambient URL | No silent default URL; always reject prod markers; staging profile runs preflight; `BOOKER_MIGRATE_ALLOW_URL` match |
| 5 | Full API+web on candidate | `staging-up.sh` starts uvicorn `:18080` + next `:13000` after migrate/seed |
| 6 | No live pay / prod seed / real users | stub only; demo seed under runtime test; preflight enforces |
| 7 | Foreign volumes | Does not `volume rm` `booker_pg`; staging uses `booker_pg_staging` |
| 8 | Negative tests | `infra/test_staging_preflight.py` — **13 PASS** |
| 9 | CI on new code | targeted pytest on this branch (not relying on bb61e998 CI alone) |

## Explicit

- `make staging-up` **not executed** on this agent (no docker; owner A says local ≠ staging score).
- Scores T10/T12/P06/O05 remain ○.
