.PHONY: help setup build-front up down logs assets assets-demo test test-borne test-mail test-sync reset

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

assets: ## Importe les elements de skin livres par le studio (SVG)
	python3 scripts/import_assets.py $(SOURCE)

assets-demo: ## Idem, plus des fonds F6+ et des variantes de teinte, pour montrer
	python3 scripts/import_assets.py $(SOURCE) --demo

test: test-borne test-bo test-mail test-sync ## Lance tous les tests (demande un PostgreSQL joignable)

test-borne: ## Teste le parcours visiteur (inscription, doublons, verification, rendu)
	cd apps/api && ../../.venv/bin/python tests/test_register_duplicate.py
	cd apps/api && ../../.venv/bin/python tests/test_render_background.py
	cd apps/api && ../../.venv/bin/python tests/test_routes_spa.py
	cd apps/api && ../../.venv/bin/python tests/test_moderation.py
	cd apps/api && ../../.venv/bin/python tests/test_materiel.py

test-bo: ## Teste la galerie des creations du back-office (filtre, tri)
	cd apps/api && ../../.venv/bin/python tests/test_designs_listing.py

test-mail: ## Teste le relais de mailing
	cd apps/api && ../../.venv/bin/python tests/test_email_format.py
	cd apps/api && ../../.venv/bin/python tests/test_relay.py
	cd apps/api && ../../.venv/bin/python tests/test_relay_chain.py

test-sync: ## Teste la remontee des donnees du stand vers le serveur
	cd apps/api && ../../.venv/bin/python tests/test_sync_chain.py

reset: ## Remet la base a zero (DESTRUCTIF)
	docker compose down -v
