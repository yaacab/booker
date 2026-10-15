# Staging provision playbook — ready after Infrastructure GO

**Status:** READY TO RUN **only** after owner Infrastructure GO (packet item 1)  
**Do not** purchase VPS / change DNS / SSH prod from this document alone.

Related: `docs/ops/evidence/2026-10-15-staging-host-proposal.md`

## Preconditions (owner)

- [ ] Infrastructure GO recorded  
- [ ] VPS created in RF region (not prod `5.45.112.180`)  
- [ ] SSH user + key for agent or operator  
- [ ] DNS `staging.bukergo.ru` A → **staging** IP only  

## Steps (operator / agent after GO)

1. **OS baseline**
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 git curl
   sudo usermod -aG docker "$USER"   # re-login
   ```

2. **Clone candidate SHA** (example: product candidate or delivery ACK SHA)
   ```bash
   sudo mkdir -p /opt/booker-staging && sudo chown "$USER":"$USER" /opt/booker-staging
   git clone https://github.com/yaacab/booker.git /opt/booker-staging/src
   cd /opt/booker-staging/src && git checkout <CANDIDATE_SHA>
   ```

3. **Secrets outside Git**
   ```bash
   sudo mkdir -p /etc/booker-staging && sudo chmod 700 /etc/booker-staging
   cp infra/env.staging.example /etc/booker-staging/secrets.env
   # edit passwords; BOOKER_RUNTIME_ENV=staging|test; PAYMENT=stub
   sudo chmod 600 /etc/booker-staging/secrets.env
   export BOOKER_STAGING_ENV_FILE=/etc/booker-staging/secrets.env
   ```

4. **Preflight + up**
   ```bash
   make staging-preflight   # or python3 infra/staging_preflight.py --env-file "$BOOKER_STAGING_ENV_FILE"
   make staging-up
   ```

5. **Record evidence**
   - `git rev-parse HEAD`
   - Alembic current revision
   - Compose project `booker-staging` only
   - Backup path under staging uploads/DB volume
   - `/health` + web URL

6. **TLS** (after DNS propagates)
   - Issue cert for `staging.bukergo.ru` only; never reuse prod certs/paths under `/opt/booker`

7. **Test roles**
   - Demo seed users only; no real customers
   - Run C01–C10 + mobile 390 against staging URL
   - Then — and only then — consider T10/T12 score evidence

8. **Stop / teardown**
   ```bash
   make staging-down
   # never docker volume rm booker_pg (prod/dev); only staging volumes when intentional
   ```

## Abort conditions

- Preflight FAIL  
- Compose publishes 5432  
- Env path under `/opt/booker` or `/etc/booker` (prod)  
- Payment provider ≠ stub  
- Any request to touch production host
