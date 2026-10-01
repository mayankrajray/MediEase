# MediEase developer commands. Every target is documented in AGENTS.md §4.
# Targets for later milestones are added in the milestone that needs them.

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

# Python API tooling runs inside the venv created in M0-P2 (apps/api/.venv).
# Until the API is containerised in M0-P5, these targets run on the host/WSL
# interpreter. See AGENTS.md §4.
API_DIR := apps/api
VENV_BIN := $(API_DIR)/.venv/bin

.PHONY: help env-check up down ps logs psql test-api lint typecheck

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env-check: ## Fail early if .env is missing
	@test -f .env || { echo "Missing .env — run: cp .env.example .env"; exit 1; }

up: env-check ## Start the local stack in the background
	$(COMPOSE) up -d --wait

down: ## Stop the local stack (data volume is kept)
	$(COMPOSE) down

ps: ## Show service status and health
	$(COMPOSE) ps

logs: ## Follow logs for all services (SERVICE=db to filter)
	$(COMPOSE) logs -f $(SERVICE)

psql: env-check ## Open a psql shell on the local database
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

test-api: ## Run the API test suite (pytest)
	cd $(API_DIR) && .venv/bin/pytest

lint: ## Lint + format-check the API (ruff)
	cd $(API_DIR) && .venv/bin/ruff check . && .venv/bin/ruff format --check .

typecheck: ## Type-check the API (mypy)
	cd $(API_DIR) && .venv/bin/mypy
