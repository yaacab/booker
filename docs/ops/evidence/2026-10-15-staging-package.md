# Stage B follow-up — staging package (LOCAL)

Date: 2026-10-15  
Git SHA: (set at commit)  
Classification: SAFE LOCAL package; **remote staging still BLOCKED**

## Deep discovery (READ-ONLY)

| Check | Result |
|---|---|
| Public DNS `staging.*` / `stage.*` | empty (prior discovery) |
| Secondary non-prod host in infra/docs | **not found** — only `5.45.112.180` / `/opt/booker` |
| `BOOKER_REMOTE` default | production VPS only |
| Docker on this CI/agent host | **unavailable** (`docker: command not found`) |
| Existing compose | [`infra/docker-compose.yml`](../../infra/docker-compose.yml) postgres+redis loopback |
| Prior postgres proof | local 2026-09-06 — not current staging |

Prod SSH was **not** attempted.

## Package delivered (reuse, not new architecture)

| Artifact | Purpose |
|---|---|
| `infra/docker-compose.staging.yml` | profile `staging`, ports `127.0.0.1:15432` / `16379`, volume `booker_pg_staging` |
| `infra/env.staging.example` | stub payments, demo seed, loopback CORS/uploads |
| `infra/staging-up.sh` | up → migrate → seed (exits 2 if no docker) |
| `infra/staging-down.sh` | tear down project `booker-staging` |
| `infra/staging-sqlite-rehearsal.sh` | LOCAL SQLite backup/restore when docker missing |
| Makefile `staging-up` / `staging-down` / `staging-sqlite-rehearsal` | entrypoints |

Dry-run deploy to production **not** prepared as executable — `deploy-vps.sh` remains prod-only and must not be pointed at staging without isolation proof.

## Ledger status

- B1 remote host: **BLOCKED**
- B1 local package: **IMPLEMENTED**
- T10/T12/P06/O05 scores: **unchanged ○** until owner ACK local-as-staging or remote URL
