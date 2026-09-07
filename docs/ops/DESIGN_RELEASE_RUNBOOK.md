# Букер: release the complete prepared design by exact commit

This procedure targets **bukergo.ru**, the documented VPS `5.45.112.180`, and existing systemd paths under `/opt/booker`. It has **not been executed on production**. Service units, effective environment, live source and database state remain runtime facts to verify. The accompanying `infra/deploy-design-release.sh` is read-only, defaults to local inspection, never connects to a host, and has no deployment mode. Exit 0 is not a release-readiness signal.

The existing `infra/deploy-vps.sh` copies into live source and changes dependencies before building, stops web during the build, then seeds production data. Do not use that path for this release. The design release needs a reviewed exact commit, an isolated build, mandatory verified backups and a brief directory switch. Preserve the user's dirty checkout; `git archive` includes only the chosen commit. Any still-uncommitted prepared design is **not included** until the release owner deliberately commits it.

## 1. Resolve the release and runtime facts

On the source machine, replace the placeholder with the approved full lowercase commit object ID. Never substitute the moving `HEAD` or a branch in the release command:

```bash
RELEASE_COMMIT=REPLACE_WITH_FULL_COMMIT_ID
bash infra/deploy-design-release.sh "$RELEASE_COMMIT"
# Optional only when the actual deployed commit has independent evidence:
# bash infra/deploy-design-release.sh "$RELEASE_COMMIT" --base FULL_PRODUCTION_COMMIT_ID
```

Use the existing SSH identity once access is available; do not invent credentials or change remote access configuration. A host operator can perform the same steps directly:

```bash
ssh -i "${BOOKER_SSH_KEY:-$HOME/.ssh/booker_deploy_key}" \
  -p "${BOOKER_SSH_PORT:-2222}" -o ForwardX11=no \
  -o StrictHostKeyChecking=yes "${BOOKER_REMOTE:-root@5.45.112.180}"
```

Verify the existing trusted host fingerprint through the operator's established channel if the key is absent. Keep the complete commit object in a separate host checkout such as `/opt/booker-release-source`; its source remote and transfer mechanism must already be trusted. Run the preflight **from that checkout**, not from `/opt/booker`. An earlier rsync deployment excluded `.git`, so a local commit ID alone does not prove the live baseline:

```bash
cd /opt/booker-release-source
bash infra/deploy-design-release.sh "$RELEASE_COMMIT" --host
```

The operator must also inspect the actual `ExecStart`, `ExecStartPre`, service drop-ins, mounts and environment files privately. Do not paste environment contents, `/proc/*/environ`, tokens or complete systemd units into release evidence. Confirm:

- `booker-web` uses `/opt/booker/apps/web` and local Next on `127.0.0.1:3030`; `booker-api` uses `/opt/booker/apps/api`, `/opt/booker/.venv`, and `127.0.0.1:8030`. Both run as `booker:booker`. Any absolute executable path or hardening setting must remain valid after the switch.
- Effective SQLite URL is `sqlite:////opt/booker/data/booker.db`; uploads live at `/opt/booker/data/uploads`. A Postgres, alternative upload or symlink layout needs a separately verified backup/switch procedure. Do not apply the commands below to it.
- Neither application directory contains runtime data, uploads, local environment files, mounted directories, custom symlinks, local hotfixes or other untracked configuration that would disappear on a directory switch. Resolve every live-only preflight entry. Keep `/opt/booker/data`, `/opt/booker/.venv`, `/etc/booker`, systemd units, nginx configuration and cron in place.
- Check every changed path against actual live files, especially API code, `models.py`, `db.py`, Alembic, `pyproject.toml`, lockfiles, infra and configuration. Never assume that a design release has no backend changes. The prepared catalog change may add `media_url` to an API response; verify its exact diff and compatibility with the live schema and old frontend.
- This runbook supports unchanged backend or an explicitly reviewed, backward-compatible API source change with **identical dependencies, schema, startup behavior and service configuration**. A schema/dependency/startup change blocks the switch until its own isolated migration/restore/dependency plan is verified. Do not restart a changed API speculatively: current startup code can modify schema and seed categories.
- Review whether any changed file outside `apps/web` and approved `apps/api` affects runtime. In particular nginx serves `/opt/booker/docs/product/LLM_DESIGN.md` as `/llms.txt`. If such a runtime asset changed, add its own snapshot/install/rollback commands before this release; do not quietly omit it or broadly rsync the repository.
- Record production build flags from the previous build configuration. Runtime `NEXT_PUBLIC_*` values cannot prove what was baked into the existing bundle. Preserve known feature flags, including Event Studio; do not turn features on merely because new design code exists.
- Freeze other deployments and seed/import/maintenance jobs for the cutover. Ensure sufficient memory and disk for npm/build, a full previous web dependency/build directory, staged source, two DB snapshots and uploads. Sibling directories must share the same filesystem for rename. Monitor current service health during the build.

## 2. Stage and build while production keeps serving

Commands below run on the host as the authorized operator after the gates above. They deliberately write only new release/backup locations until the cutover section. Keep all commands in the same shell so the variables and lock persist. Never rerun using an existing stage or backup directory:

```bash
set -euo pipefail
umask 077
SOURCE_REPO=/opt/booker-release-source
# RELEASE_COMMIT must still contain the exact ID reviewed above.
[[ "$RELEASE_COMMIT" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]
[[ "$(git -C "$SOURCE_REPO" cat-file -t "$RELEASE_COMMIT")" == commit ]]
exec 9>/run/lock/booker-design-release.lock
flock -n 9
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="/opt/booker-design-${RELEASE_COMMIT:0:12}-${STAMP}"
BACKUP="/var/backups/booker/design-${RELEASE_COMMIT:0:12}-${STAMP}"
[[ ! -e "$STAGE" && ! -e "$BACKUP" ]]
mkdir -m 0755 "$STAGE"
mkdir -m 0700 "$BACKUP"
git -C "$SOURCE_REPO" archive --format=tar "$RELEASE_COMMIT" | tar -x -C "$STAGE"
printf '%s\n' "$RELEASE_COMMIT" > "$BACKUP/release-commit.txt"
printf '%s\n' "STAMP=$STAMP" "STAGE=$STAGE" "BACKUP=$BACKUP" \
  > "$BACKUP/runtime-paths.txt"
stat -c '%d %n' /opt/booker/apps "$STAGE/apps"
```

The two device IDs must match. Treat all code and package lifecycle scripts as the reviewed release's executable code; build as the unprivileged service user. Preserve the same Node/npm major versions used in production. Use an explicit known flag set and a clean environment; do not copy an unknown `.env` from the live checkout. Example for the documented endpoints and Event Studio flag off, **only if those match the reviewed release configuration**:

```bash
chown -R booker:booker "$STAGE"
chmod 0755 "$STAGE" "$STAGE/apps" "$STAGE/apps/web"
runuser -u booker -- env -i PATH=/usr/local/bin:/usr/bin:/bin \
  HOME="$STAGE" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=/api NEXT_PUBLIC_SITE_URL=https://bukergo.ru \
  NEXT_PUBLIC_EVENT_STUDIO_MAP_V1=0 \
  BOOKER_INTERNAL_API_URL=http://127.0.0.1:8030 \
  bash -c 'set -euo pipefail; cd "$1/apps/web"; npm ci; npm run lint; npm run test:unit; npm run build' _ "$STAGE"
test -s "$STAGE/apps/web/.next/BUILD_ID"
runuser -u booker -- test -r "$STAGE/apps/web/.next/BUILD_ID"
```

The build may fetch public read endpoints from the existing API (catalog, artists, venues, sitemap); review those calls. For a release requiring new API behavior during build, first prove it against an isolated restored DB and API, then use that API's loopback URL. Never run production signup/payment/booking/seed tests or production mutation endpoints as build validation. Set only the matching runtime URL for the final production process. A resource-starved host needs an equivalent external Linux build environment or additional capacity; do not stop live web to make this build fit.

Start a candidate web process on an unused loopback port, with the same environment and flags, through a separate transient service. The example assumes `3130` is free; verify that first. No nginx or production unit changes are needed:

```bash
ss -ltn '( sport = :3130 )'
# Continue only if no listener is present.
CANDIDATE="booker-design-${STAMP}"
systemd-run --unit="$CANDIDATE" --collect \
  --property=User=booker --property=Group=booker \
  --property="WorkingDirectory=$STAGE/apps/web" \
  --setenv=NODE_ENV=production \
  --setenv=NEXT_PUBLIC_API_URL=/api \
  --setenv=NEXT_PUBLIC_SITE_URL=https://bukergo.ru \
  --setenv=BOOKER_INTERNAL_API_URL=http://127.0.0.1:8030 \
  /usr/bin/node "$STAGE/apps/web/node_modules/next/dist/bin/next" start -H 127.0.0.1 -p 3130
curl --fail --silent --show-error --retry 10 --retry-connrefused \
  --retry-delay 1 --max-time 15 --output /dev/null http://127.0.0.1:3130/
```

Verify the prepared public routes, fonts, profile media, search, legal and login pages. Verify authenticated design flows against staging/test data in an isolated environment; a production GET smoke alone is not that evidence. Candidate `/api` calls need a matching private reverse proxy/tunnel if exercised in a browser; do not expose candidate ports or redirect real users to them. Stop the exact candidate unit before the directory switch:

```bash
systemctl stop "$CANDIDATE"
```

## 3. Snapshot and short switch

Before stopping anything, capture the current source/configuration, previous BUILD_ID and manifest checksums into the private backup directory. Retained old application directories below are the authoritative previous runnable build and dependencies. Back up systemd/nginx/environment files privately only if the operator needs them; this release does not replace them. Run a preliminary SQLite `.backup` plus `PRAGMA integrity_check` while live, so unsupported/corrupt backup conditions are discovered before downtime:

```bash
cp -a /opt/booker/apps/web/.next/BUILD_ID "$BACKUP/previous-BUILD_ID"
sqlite3 -readonly /opt/booker/data/booker.db ".timeout 10000" ".backup '$BACKUP/preliminary.db'"
test "$(sqlite3 -readonly "$BACKUP/preliminary.db" 'PRAGMA integrity_check;')" = ok
```

Prepare and privately review the entire switch block before executing it. Set `SWITCH_API=1` only for the companion API change that passed the explicit gate; otherwise keep `0`. This example stops both services briefly to obtain a DB/uploads snapshot from the same quiesced interval. Confirm all other DB/upload writers are stopped too. Backup failure is fatal and must restart the existing services; never continue without the snapshot. The final snapshot contains sensitive production data: retain mode `0700` and do not upload it to ChatGPT or a public location.

```bash
SWITCH_API=0
[[ "$SWITCH_API" == 0 || "$SWITCH_API" == 1 ]]
OLD_WEB="/opt/booker/apps/web.previous-${STAMP}"
OLD_API="/opt/booker/apps/api.previous-${STAMP}"
printf '%s\n' "SWITCH_API=$SWITCH_API" "OLD_WEB=$OLD_WEB" "OLD_API=$OLD_API" \
  >> "$BACKUP/runtime-paths.txt"
[[ ! -e "$OLD_WEB" && ! -e "$OLD_API" ]]
test -s "$STAGE/apps/web/.next/BUILD_ID"
# Do not execute until the rollback commands below are ready in another trusted session.
systemctl stop booker-web booker-api
if ! (
  set -euo pipefail
  [[ "$(systemctl show booker-web -p MainPID --value)" == 0 ]]
  [[ "$(systemctl show booker-api -p MainPID --value)" == 0 ]]
  sqlite3 -readonly /opt/booker/data/booker.db ".timeout 10000" ".backup '$BACKUP/booker.db'"
  test "$(sqlite3 -readonly "$BACKUP/booker.db" 'PRAGMA integrity_check;')" = ok
  sqlite3 -readonly "$BACKUP/booker.db" 'SELECT 1 FROM users LIMIT 1;' >/dev/null
  if [[ -d /opt/booker/data/uploads ]]; then
    cp -a /opt/booker/data/uploads "$BACKUP/uploads"
  else
    mkdir "$BACKUP/uploads"
  fi
  tar --exclude='./data' --exclude='./.venv' --exclude='./.git' \
    --exclude='./apps/web/node_modules' --exclude='./apps/web/.next/cache' \
    -cpf "$BACKUP/live-code-and-build.tar" -C /opt/booker .
  tar -tf "$BACKUP/live-code-and-build.tar" >/dev/null
  sha256sum "$BACKUP/booker.db" "$BACKUP/live-code-and-build.tar" > "$BACKUP/SHA256SUMS"
); then
  systemctl start booker-api booker-web
  echo 'Snapshot failed; existing application retained.' >&2
  exit 1
fi

# Each rename is atomic; the two-renames pair is not. Services are stopped.
mv /opt/booker/apps/web "$OLD_WEB"
mv "$STAGE/apps/web" /opt/booker/apps/web
if [[ "$SWITCH_API" == 1 ]]; then
  mv /opt/booker/apps/api "$OLD_API"
  mv "$STAGE/apps/api" /opt/booker/apps/api
fi
systemctl start booker-api
curl --fail --silent --show-error --retry 10 --retry-connrefused \
  --retry-delay 1 --max-time 15 http://127.0.0.1:8030/health
systemctl start booker-web
curl --fail --silent --show-error --retry 10 --retry-connrefused \
  --retry-delay 1 --max-time 15 --output /dev/null http://127.0.0.1:3030/
curl --fail --silent --show-error --retry 5 --max-time 15 \
  --output /dev/null https://bukergo.ru/
systemctl is-active booker-api booker-web
printf '%s\n' "$RELEASE_COMMIT" > "$BACKUP/activated-commit.txt"
cp -a /opt/booker/apps/web/.next/BUILD_ID "$BACKUP/activated-BUILD_ID"
```

Shell failure after the snapshot block does **not** imply automatic rollback. The operator must immediately use the commands below for a failed rename/start/smoke, including an interrupted terminal. Do not run broad `pkill`, migrations, `pip install`, seed/enrichment commands, `daemon-reload` or nginx reload as part of this design switch. Current systemd paths and reverse proxy remain intact. Preserve the old directories, stage and backup until the release is accepted and retention is deliberately handled.

## 4. Rollback and acceptance

Use the recorded paths from this release, not a wildcard or the most recently named directory. If connectivity was interrupted, first reconstruct `STAMP`, `OLD_WEB`, `OLD_API`, `BACKUP` and `SWITCH_API` from the private release record and inspect which renames actually completed. Old directories retain the previous dependencies and `.next`; restoring `.next` alone cannot roll back changed source/dependencies.

```bash
systemctl stop booker-web booker-api
if [[ -d "$OLD_WEB" ]]; then
  if [[ -e /opt/booker/apps/web ]]; then
    mv /opt/booker/apps/web "/opt/booker/apps/web.failed-${STAMP}"
  fi
  mv "$OLD_WEB" /opt/booker/apps/web
fi
if [[ "$SWITCH_API" == 1 && -d "$OLD_API" ]]; then
  if [[ -e /opt/booker/apps/api ]]; then
    mv /opt/booker/apps/api "/opt/booker/apps/api.failed-${STAMP}"
  fi
  mv "$OLD_API" /opt/booker/apps/api
fi
test -s /opt/booker/apps/web/.next/BUILD_ID
systemctl start booker-api booker-web
curl --fail --silent --show-error --retry 10 --retry-connrefused \
  --retry-delay 1 --max-time 15 http://127.0.0.1:8030/health
curl --fail --silent --show-error --retry 10 --retry-connrefused \
  --retry-delay 1 --max-time 15 --output /dev/null https://bukergo.ru/
systemctl is-active booker-api booker-web
```

Do not restore the DB automatically on a design rollback: once API resumes, real users may have new writes. A DB restore requires an incident-specific decision, all writers stopped, a fresh rescue backup and reconciliation of later data. The no-schema-change gate keeps this application rollback compatible with the live database. If startup changed schema or unexpectedly mutated data, stop and assess that incident explicitly.

After a successful switch, verify HTTPS/TLS, homepage, catalog/search, profile images, login, legal pages, prepared workspaces and read-only authenticated navigation using a designated account. Confirm release commit and BUILD_ID, inspect new service errors without publishing sensitive log content, and watch 5xx/latency. Record the exact diff, tests, backup integrity, restore verification, switch time, smoke results and any remaining limitations. The preliminary/final SQLite copies are verified by integrity and table-read checks; a full separate restore drill remains additional evidence, not something to claim from these checks alone.

**Readiness:** local preparation is complete only when the exact commit is available and validated. Production is ready only after live facts, scope/compatibility, candidate build, snapshots and rollback are verified. **Current access risk:** no production connection or deployment is performed by these files; a host operator with existing access must execute the verified procedure.
