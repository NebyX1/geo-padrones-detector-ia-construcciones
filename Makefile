.PHONY: up down build test models data status
COMPOSE = docker compose -f docker-compose.yml -f docker-compose.dev.yml

up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down
build:
	$(COMPOSE) build
status:
	$(COMPOSE) ps
models:
	$(COMPOSE) run --rm models
test:
	python -m pytest backend/tests
	npm --prefix frontend test
	npm --prefix frontend run lint
	npm --prefix frontend run build
data:
	python scripts/download_cadastre.py
	python scripts/import_cadastre.py data/raw/lavalleja.ndjson
