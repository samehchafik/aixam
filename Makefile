.PHONY: help setup build-front up down logs seed test-mail reset

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Copie .env, installe les deps front
	@test -f .env || cp .env.example .env
	cd apps/kiosk && npm install
	cd apps/admin && npm install

build-front: ## Compile les deux SPA dans apps/api/static/
	cd apps/kiosk && npm run build
	cd apps/admin && npm run build
	rm -rf apps/api/static
	mkdir -p apps/api/static
	cp -R apps/kiosk/dist apps/api/static/kiosk
	cp -R apps/admin/dist apps/api/static/admin

up: build-front ## Build front puis demarre la stack docker
	docker compose up -d --build

down: ## Arrete la stack
	docker compose down

logs: ## Suit les logs api + worker
	docker compose logs -f api worker

seed: ## Genere fonds/objets de demo + index.json (a remplacer par les assets AIXAM)
	.venv/bin/python scripts/generate_assets.py

test-mail: ## Teste le relais de mailing (demande un PostgreSQL joignable)
	cd apps/api && ../../.venv/bin/python tests/test_relay.py
	cd apps/api && ../../.venv/bin/python tests/test_relay_chain.py

reset: ## Remet la base a zero (DESTRUCTIF)
	docker compose down -v
