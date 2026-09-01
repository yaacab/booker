.PHONY: init test-api lint web-build web-lint check seed deploy wait-dns migrate migrate-docker

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
	cd apps/api && $(PYTHON) -m booker_api.seed

migrate:
	cd apps/api && $(PYTHON) -m alembic upgrade head

migrate-docker:
	./infra/migrate-postgres-docker.sh

deploy:
	bash infra/deploy-vps.sh

wait-dns:
	bash infra/wait-dns.sh
