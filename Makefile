.PHONY: init test-api lint web-build web-lint check seed seed-venues-moscow seed-founding-artists deploy wait-dns migrate migrate-docker fetch-venues-moscow merge-venues-moscow e2e-smoke staging-up staging-down staging-sqlite-rehearsal staging-preflight test-staging-preflight

PYTHON ?= $(CURDIR)/.venv/bin/python

init:
	PYENV_VERSION=3.11.6 python3 -m venv .venv
	$(PYTHON) -m pip install -e "apps/api[dev]"
	cd apps/web && npm install

test-api:
	cd apps/api && $(PYTHON) -m pytest -q

lint:
	cd apps/api && $(PYTHON) -m ruff check booker_api tests

web-lint:
	cd apps/web && npx tsc --noEmit

web-build:
	cd apps/web && npm run build

check: test-api lint

# Узкий Playwright smoke (нужны локальные API+web). Не в default CI.
e2e-smoke:
	cd apps/web && npx playwright test e2e/flow.spec.ts --reporter=line

seed:
	cd apps/api && BOOKER_ALLOW_DEMO_SEED=1 $(PYTHON) -m booker_api.seed

seed-venues-moscow:
	cd apps/api && $(PYTHON) -m booker_api.seed_venues_moscow

# Идемпотентно добирает founding-артистов (без demo-users / wipe).
seed-founding-artists:
	cd apps/api && $(PYTHON) -c "from booker_api.db import SessionLocal; from booker_api.seed import enrich_catalog; db=SessionLocal(); print({'catalog_added': enrich_catalog(db)}); db.commit()"

fetch-venues-moscow:
	mkdir -p /tmp/booker-venues
	$(PYTHON) scripts/fetch_osm_venues_moscow.py --out /tmp/booker-venues/osm_venues_raw.json || echo "warning: OSM venues fetch failed, continuing"
	$(PYTHON) scripts/fetch_wikidata_venues_moscow.py --out /tmp/booker-venues/wikidata_venues_raw.json || echo "warning: Wikidata venues fetch failed, continuing"
	$(PYTHON) scripts/fetch_datamos_culture_venues.py --out /tmp/booker-venues/datamos_culture_raw.json || echo "warning: data.mos culture venues fetch failed, continuing"

merge-venues-moscow:
	$(PYTHON) scripts/merge_moscow_venues_open.py \
		--curated $${CURATED:-/tmp/moscow_venues_wave1.json} \
		--osm /tmp/booker-venues/osm_venues_raw.json \
		--wikidata /tmp/booker-venues/wikidata_venues_raw.json \
		--datamos /tmp/booker-venues/datamos_culture_raw.json \
		--out data/moscow_venues_open.json \
		--target 300

migrate:
	cd apps/api && $(PYTHON) -m alembic upgrade head

# Local docker-compose.yml (port 5432). No credential defaults in Git.
# Example (secrets stay in your shell, not in the Makefile):
#   export BOOKER_DATABASE_URL='postgresql+psycopg://USER:{{LOCAL_PG_PASSWORD}}@127.0.0.1:5432/booker'
#   # replace {{LOCAL_PG_PASSWORD}} before running
migrate-docker:
	@test -n "$$BOOKER_DATABASE_URL" || (echo "Set BOOKER_DATABASE_URL (no Makefile default)" >&2; exit 2)
	BOOKER_MIGRATE_PROFILE=local-docker ./infra/migrate-postgres-docker.sh

deploy:
	bash infra/deploy-vps.sh

wait-dns:
	bash infra/wait-dns.sh

# Isolated staging harness (loopback). Requires BOOKER_STAGING_ENV_FILE outside Git.
# LOCAL level — does not close T10/T12 without owner ACK.
staging-up:
	@test -n "$$BOOKER_STAGING_ENV_FILE" || (echo "Set BOOKER_STAGING_ENV_FILE=/tmp/booker-staging/secrets.env" >&2; exit 2)
	BOOKER_MIGRATE_PROFILE=staging bash infra/staging-up.sh

staging-down:
	bash infra/staging-down.sh

staging-preflight:
	@test -n "$$BOOKER_STAGING_ENV_FILE" || (echo "Set BOOKER_STAGING_ENV_FILE=..." >&2; exit 2)
	python3 infra/staging_preflight.py --env-file "$$BOOKER_STAGING_ENV_FILE"

# LOCAL SQLite fallback when Docker is unavailable (does not close T10/O05).
staging-sqlite-rehearsal:
	bash infra/staging-sqlite-rehearsal.sh

test-staging-preflight:
	apps/api/.venv/bin/python -m pytest -q infra/test_staging_preflight.py

