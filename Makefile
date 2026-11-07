# Órdenes de desarrollo. Todo corre en Docker: no hace falta Python ni Node en el equipo.
#   make check     → todo lo que comprueba el CI (lint, tipos, pruebas)
#   make dev       → web con recarga en 127.0.0.1:5173 contra el backend de compose (127.0.0.1:8010)

SHELL := /bin/sh
UID_GID := $(shell id -u):$(shell id -g)
DEV_IMAGE := carrete:dev
NODE_IMAGE := node:22-alpine
TEST_NET := carrete-test
TEST_DB := carrete-test-db
TEST_DB_URL := postgresql+psycopg://carrete:pruebas@$(TEST_DB)/carrete

PY := docker run --rm -u $(UID_GID) -e HOME=/tmp -e RUFF_CACHE_DIR=/tmp/ruff -e MYPY_CACHE_DIR=/tmp/mypy \
	--network $(TEST_NET) -e CARRETE_TEST_DATABASE_URL=$(TEST_DB_URL) -v $(CURDIR):/src $(DEV_IMAGE)
NODE := docker run --rm -u $(UID_GID) -e HOME=/tmp -e npm_config_cache=/tmp/npm -v $(CURDIR)/web:/web -w /web $(NODE_IMAGE)

.PHONY: help dev-image test-db test-db-stop backend-lint backend-test web-install web-lint web-test \
	openapi openapi-check check image up down logs dev

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

dev-image: ## Construye la imagen de desarrollo (Python + dependencias de pruebas)
	docker build -f deploy/Dockerfile --target dev -t $(DEV_IMAGE) .

test-db: ## Arranca un PostgreSQL desechable para las pruebas
	@docker network inspect $(TEST_NET) >/dev/null 2>&1 || docker network create $(TEST_NET) >/dev/null
	@docker inspect $(TEST_DB) >/dev/null 2>&1 || docker run -d --name $(TEST_DB) --network $(TEST_NET) \
		--tmpfs /var/lib/postgresql/data -e POSTGRES_USER=carrete -e POSTGRES_PASSWORD=pruebas \
		-e POSTGRES_DB=carrete postgres:17-alpine >/dev/null
	@until docker exec $(TEST_DB) pg_isready -U carrete -q; do sleep 1; done

test-db-stop: ## Elimina el PostgreSQL de pruebas
	-docker rm -f $(TEST_DB) >/dev/null 2>&1
	-docker network rm $(TEST_NET) >/dev/null 2>&1

backend-lint: test-db ## ruff, formato, mypy --strict y bandit
	$(PY) sh -c 'ruff check app tests && ruff format --check app tests && mypy app && bandit -q -c pyproject.toml -r app'

backend-test: test-db ## Pruebas del backend con cobertura (mínimo 85 %)
	$(PY) python -m pytest -p no:cacheprovider --cov

web-install: ## Instala las dependencias de la web (según package-lock.json)
	$(NODE) npm ci --no-audit --no-fund

web-lint: ## Tipos, ESLint y Prettier de la web
	$(NODE) sh -c 'npm run -s typecheck && npm run -s lint && npm run -s format:check'

web-test: ## Pruebas de la web con cobertura (mínimo 70 %)
	$(NODE) npm run -s test:coverage

openapi: test-db ## Regenera la especificación OpenAPI y los tipos TypeScript de la web
	$(PY) python -m app.cli openapi > web/src/api/openapi.json
	$(NODE) npm run -s api:types

openapi-check: openapi ## Falla si el cliente TypeScript no está al día con la API
	git diff --exit-code -- web/src/api/

check: backend-lint backend-test web-lint web-test ## Todo lo que comprueba el CI

image: ## Construye la imagen de producción
	docker build -f deploy/Dockerfile --target runtime -t ghcr.io/javier-hernaez/carrete:latest \
		--build-arg CARRETE_VERSION=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) .

up: ## Arranca Carrete (deploy/docker-compose.yml)
	cd deploy && docker compose up -d

down: ## Para Carrete (los datos se conservan)
	cd deploy && docker compose down

logs: ## Registros de app y worker
	cd deploy && docker compose logs -f --tail=100 app worker

dev: ## Web con recarga en caliente contra el backend de compose
	docker run --rm -it -u $(UID_GID) -e HOME=/tmp --network host -v $(CURDIR)/web:/web -w /web \
		$(NODE_IMAGE) npm run dev -- --host 127.0.0.1
