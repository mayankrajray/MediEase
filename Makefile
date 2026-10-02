# MediEase developer commands. Every target is documented in AGENTS.md §4.
# Targets for later milestones are added in the milestone that needs them.

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

# API tooling runs in a virtualenv at apps/api/.venv until the API is
# containerised (M0-P5). Override the interpreter with: make install-api PYTHON=...
API_DIR := apps/api
VENV_BIN := .venv/bin
PYTHON ?= python3.12

# Database tests run against the compose `db` through its localhost port.
# POSTGRES_* come from .env (optional here; env-check guards the targets that need it).
# The URL reaches pytest through the environment, so it is never echoed.
-include .env
TEST_DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)
export TEST_DATABASE_URL

.PHONY: help env-check up down ps logs psql migrate install-api api-venv-check test test-api lint typecheck

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env-check: ## Fail early if .env is missing
	@test -f .env || { echo "Missing .env — run: cp .env.example .env"; exit 1; }

up: env-check ## Build images and start the stack: db -> migrate -> api
	$(COMPOSE) up -d --wait --build

down: ## Stop the local stack (data volume is kept)
	$(COMPOSE) down

migrate: env-check ## Re-run database migrations (make up already runs them)
	$(COMPOSE) run --rm --build migrate

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

api-venv-check:
	@test -x $(API_DIR)/$(VENV_BIN)/python || { echo "Missing $(API_DIR)/.venv — run: make install-api"; exit 1; }

test: test-api ## Run all test suites (web joins in M0-P4)

test-api: env-check api-venv-check ## Run the API test suite (needs the db: make up)
	cd $(API_DIR) && $(VENV_BIN)/pytest -q

lint: api-venv-check ## Lint and format-check the API (ruff)
	cd $(API_DIR) && $(VENV_BIN)/ruff check . && $(VENV_BIN)/ruff format --check .

typecheck: api-venv-check ## Type-check the API (mypy)
	cd $(API_DIR) && $(VENV_BIN)/mypy
