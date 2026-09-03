.PHONY: init test-api lint web-build web-lint check seed seed-venues-moscow deploy wait-dns migrate migrate-docker fetch-venues-moscow merge-venues-moscow

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

seed:
	cd apps/api && BOOKER_ALLOW_DEMO_SEED=1 $(PYTHON) -m booker_api.seed

seed-venues-moscow:
	cd apps/api && $(PYTHON) -m booker_api.seed_venues_moscow

fetch-venues-moscow:
	mkdir -p /tmp/booker-venues
	$(PYTHON) scripts/fetch_osm_venues_moscow.py --out /tmp/booker-venues/osm_venues_raw.json || true
	$(PYTHON) scripts/fetch_wikidata_venues_moscow.py --out /tmp/booker-venues/wikidata_venues_raw.json
	-$(PYTHON) scripts/fetch_datamos_culture_venues.py --out /tmp/booker-venues/datamos_culture_raw.json

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

migrate-docker:
	./infra/migrate-postgres-docker.sh

deploy:
	bash infra/deploy-vps.sh

wait-dns:
	bash infra/wait-dns.sh
