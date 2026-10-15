# Option C — separate staging host proposal (not purchased)

Date: 2026-10-15  
Status: **READY FOR OWNER GO** — no purchase/create without explicit approval  
Option B: remote staging DNS empty (`staging.*` / `stage.*` / `test.bukergo.ru`) — not found

## Why

Owner decision: local tests (A) do **not** auto-count as staging scores. Separate host required for T10/T12/P06/O05 unless later ACK changes policy.

## Minimal resources (RF region, 152-ФЗ)

| Item | Recommendation |
|---|---|
| Compute | 1× VPS 2 vCPU / 2–4 GB RAM / 40 GB SSD |
| OS | Ubuntu 22.04/24.04 LTS |
| Region | РФ (Selectel / Timeweb / Yandex Cloud RU) |
| Est. cost | ~500–1500 ₽/мес (verify current tariff before GO) |
| DNS | `staging.bukergo.ru` A → staging IP only (not prod `5.45.112.180`) |
| TLS | Let's Encrypt after DNS |

## Isolation rules

- Separate VM from prod `5.45.112.180`
- Separate DB volume, uploads under `/opt/booker-staging/` (not `/opt/booker`)
- `BOOKER_RUNTIME_ENV=staging` or `test`
- `BOOKER_PAYMENT_PROVIDER=stub` only
- Demo seed allowed; no real users
- Deploy via copy of hardened `infra/staging-*` + secrets **outside** Git on the host
- Firewall: SSH key-only; HTTP(S) public optional for browser E2E

## Launch plan (after GO)

Full command sequence: `docs/ops/STAGING_PROVISION_PLAYBOOK.md`.

1. Owner purchases/creates VPS and shares SSH user + IP (or grants agent key).
2. Agent installs docker, clones candidate SHA, places secrets under `/etc/booker-staging/` (0600).
3. `BOOKER_STAGING_ENV_FILE=... make staging-up` after preflight PASS.
4. Record deployed SHA, alembic revision, backup path.
5. Run C01–C10 + mobile on staging URL → then score T10/T12 only with evidence.

## Explicit non-actions until GO

- No payment for VPS
- No DNS change
- No SSH to production
- No migrate on remote without permission
