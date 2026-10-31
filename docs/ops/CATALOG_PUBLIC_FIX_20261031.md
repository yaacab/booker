# Catalog public fix — 2026-10-31

**Готовность:** FULL 59,00% / MVP 56,00% / Design 15,00% (без пересчёта).

## Cause

Founding artists (~30) lived in orgs **without TeamMember**. API public search skips those (`_has_account`). One QA-only artist stays excluded by design.

## Code fix (branch `sync/live-canonical-20261031` @ `cf5b506`)

1. **API** — on startup `link_orphan_verified_artists()` attaches `catalog-steward@bukergo.ru` as owner to verified artist orgs with zero members. QA orgs unchanged. Tests in `test_catalog_unfilled_calendar.py` PASS (7).
2. **Web** — honest empty copy in search + M04; briefs no longer promise a public venue photo grid; guest cabinet hides metrics/logout until login.

## Deploy (owner / machine with SSH to `5.45.112.180`)

This agent **cannot** reach prod SSH from the current environment (banner timeout).

```bash
# From a host that can SSH to the VPS — adapt to your release layout:
# 1) Deploy web+api from sync/live-canonical-20261031 (or copy the 7 changed files
#    into the live release trees matching 20261023-prod-fixes-w6b / 20261023-qa-wave2).
# 2) Restart API so lifespan runs the linker:
sudo systemctl restart booker-api
sudo systemctl restart booker-web   # if web unit separate
# 3) Verify:
curl -sS 'https://bukergo.ru/api/catalog/search?kind=artist&limit=5' | head -c 400
```

Optional one-shot without full redeploy (API package already updated on disk):

```bash
cd /opt/booker/current/apps/api   # or active release path
sudo -u booker BOOKER_…=… ./venv/bin/python - <<'PY'
from booker_api.db import SessionLocal
from booker_api.seed import link_orphan_verified_artists
db = SessionLocal()
n = link_orphan_verified_artists(db)
db.commit()
print({"linked": n})
PY
```

## Expect after deploy

- `/search?kind=artist` shows founding verified artists (not QA).
- M04 artist empty state no longer blames the date when catalog is empty.
- `/briefs` teaser points to `/events/new`, not venue stub.
- `/cabinet/performer` without session: login CTA only, no zero metrics / logout.
- Public venues remain intentionally closed (research set).

## Explicit non-claims

- No production deploy performed from this session.
- End-to-end booking path after linker not re-run on live data here.
