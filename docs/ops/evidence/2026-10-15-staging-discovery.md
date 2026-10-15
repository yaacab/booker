# Stage B — Staging discovery (READ-ONLY)

Date: 2026-10-15  
Candidate SHA: `bb61e998f52b4eafd5a13efbb39567a57e7435d2`  
Classification: READ-ONLY (no deploy, no SSH mutation, no DB writes)

## Findings

| Check | Result |
|---|---|
| `staging.bukergo.ru` / `stage.bukergo.ru` DNS | **NXDOMAIN / empty** — no A record |
| `bukergo.ru` | A `5.45.112.180`, HTTPS 200 (nginx + Next) — **production** |
| `www.bukergo.ru`, `bookergo.ru` | 301 → `https://bukergo.ru/` |
| nginx config hosts | only prod names in `infra/nginx/bukergo.ru.conf` |
| Deploy remote default | `root@5.45.112.180` via `infra/deploy-vps.sh` |
| Documented DB | prod SQLite `/opt/booker/data/booker.db` (`PROD_INFRA.md`) |
| Separate staging VM / URL in repo | **not found** |
| Local Postgres docker proof (2026-09-06) | exists; **not** current staging |
| Local restore drills | PASS on synthetic SQLite; explicitly not staging API recovery |

## Relation to production

Single documented runtime host: `5.45.112.180`. Using it as staging would violate isolation and mission production bans. Not probed via SSH; deploy key presence not assumed as permission.

## Verdict

**BLOCKED** — isolated staging environment is not discoverable from repository + public DNS.

### Owner request (to unblock B / T10 / T12 / P06 / O05)

1. Staging URL (or confirm only local harness is allowed until a host exists).
2. DB engine + Alembic revision on that environment.
3. Test role credentials (customer / performer / venue / operator) — non-prod.
4. Backup path + allowed restore drill target.
5. Confirmation that production `5.45.112.180` must not be used for acceptance mutations.

## Parallel path

Local isolated acceptance on candidate SHA (SQLite seed + pytest / Playwright) proceeds for Stage C evidence at level **локально**. Staging points in `PROJECT_PROGRESS.md` remain `○` (0 п.п. change).
