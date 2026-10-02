# MediEase developer commands. Every target is documented in AGENTS.md §4.
# Targets for later milestones are added in the milestone that needs them.

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

# API tooling runs in a virtualenv at apps/api/.venv and web tooling in
# apps/web/node_modules until both apps are containerised (M0-P5). On Windows run
# make inside WSL with Python 3.12 and Node (apps/web/.nvmrc) installed there.
# Override the Python interpreter with: make install-api PYTHON=...
API_DIR := apps/api
WEB_DIR := apps/web
VENV_BIN := .venv/bin
PYTHON ?= python3.12

# Database tests run against the compose `db` through its localhost port.
# POSTGRES_* come from .env (optional here; env-check guards the targets that need it).
# The URL reaches pytest through the environment, so it is never echoed.
-include .env
TEST_DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)
export TEST_DATABASE_URL

# NFR-14: >= 80% on the business core, on top of the >= 90% whole-package gate
# in pyproject.toml. CI runs the same command (.github/workflows/ci.yml).
CORE_COVERAGE := --include='*/mediease_api/domain/*,*/mediease_api/application/*' --fail-under=80

.PHONY: help env-check up down ps logs psql migrate seed smoke install-api install-web api-venv-check \
	web-deps-check test test-api test-web lint lint-api lint-web typecheck typecheck-api \
	typecheck-web dev-web contract contract-check audit

help: ## List available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(firstword $(MAKEFILE_LIST)) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

env-check: ## Fail early if .env is missing
	@test -f .env || { echo "Missing .env — run: cp .env.example .env"; exit 1; }

up: env-check ## Build images and start the stack: db -> migrate -> api -> web
	$(COMPOSE) up -d --wait --build

smoke: ## Check the running stack end to end, incl. least privilege (make up first)
	API_PORT=$(or $(API_PORT),8000) WEB_PORT=$(or $(WEB_PORT),3000) bash scripts/smoke.sh

down: ## Stop the local stack (data volume is kept)
	$(COMPOSE) down

migrate: env-check ## Re-run database migrations (make up already runs them)
	$(COMPOSE) run --rm --build migrate

seed: env-check ## Load synthetic demo data (APP_ENV=local only; make up first)
	$(COMPOSE) run --rm --no-deps api python -m mediease_api.delivery.cli.seed

ps: ## Show service status and health
	$(COMPOSE) ps

logs: ## Follow logs for all services (SERVICE=db to filter)
	$(COMPOSE) logs -f $(SERVICE)

psql: env-check ## Open a psql shell on the local database
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

install-api: ## Create apps/api/.venv and install the API with dev tools
	@command -v $(PYTHON) >/dev/null || { echo "$(PYTHON) not found — install Python 3.12 (see README)"; exit 1; }
	cd $(API_DIR) && { test -x $(VENV_BIN)/python || $(PYTHON) -m venv .venv; } \
		&& $(VENV_BIN)/python -m pip install --upgrade pip \
		&& $(VENV_BIN)/python -m pip install --prefer-binary -e ".[dev]"

install-web: ## Install the web app's exact dependencies from package-lock.json
	@command -v node >/dev/null || { echo "node not found — install Node $$(cat $(WEB_DIR)/.nvmrc) (see README)"; exit 1; }
	cd $(WEB_DIR) && npm ci

api-venv-check:
	@test -x $(API_DIR)/$(VENV_BIN)/python || { echo "Missing $(API_DIR)/.venv — run: make install-api"; exit 1; }

web-deps-check:
	@test -d $(WEB_DIR)/node_modules || { echo "Missing $(WEB_DIR)/node_modules — run: make install-web"; exit 1; }

test: test-api test-web ## Run all test suites

test-api: env-check api-venv-check ## Run the API tests with both coverage gates (needs the db: make up)
	cd $(API_DIR) && $(VENV_BIN)/pytest -q --cov && $(VENV_BIN)/coverage report $(CORE_COVERAGE)

test-web: web-deps-check ## Run the web test suite (Vitest)
	cd $(WEB_DIR) && npm test -- --run

lint: lint-api lint-web ## Lint API (ruff, layer boundaries) and web (ESLint)

lint-api: api-venv-check
	cd $(API_DIR) && $(VENV_BIN)/ruff check . && $(VENV_BIN)/ruff format --check . && $(VENV_BIN)/lint-imports

lint-web: web-deps-check
	cd $(WEB_DIR) && npm run -s lint

typecheck: typecheck-api typecheck-web ## Type-check API (mypy) and web (tsc)

typecheck-api: api-venv-check
	cd $(API_DIR) && $(VENV_BIN)/mypy

typecheck-web: web-deps-check
	cd $(WEB_DIR) && npm run -s typecheck

dev-web: web-deps-check ## Run the web app on :3000 against the API on localhost (make up first)
	cd $(WEB_DIR) && API_INTERNAL_URL=http://localhost:$(or $(API_PORT),8000) npm run dev

contract: web-deps-check ## Regenerate web API types from contracts/openapi.yaml (ADR-0008)
	cd $(WEB_DIR) && npm run -s gen:api

contract-check: web-deps-check ## Fail if the committed web API types are out of date
	cd $(WEB_DIR) && npm run -s gen:api:check

audit: api-venv-check web-deps-check ## Check API and web dependencies for known vulnerabilities
	cd $(API_DIR) && $(VENV_BIN)/pip-audit --skip-editable
	cd $(WEB_DIR) && npm audit --audit-level=high
