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

.PHONY: help env-check up down ps logs psql install-api api-venv-check test test-api lint typecheck

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

install-api: ## Create apps/api/.venv and install the API with dev tools
	@command -v $(PYTHON) >/dev/null || { echo "$(PYTHON) not found — install Python 3.12 (see README)"; exit 1; }
	cd $(API_DIR) && { test -x $(VENV_BIN)/python || $(PYTHON) -m venv .venv; } \
		&& $(VENV_BIN)/python -m pip install --upgrade pip \
		&& $(VENV_BIN)/python -m pip install --prefer-binary -e ".[dev]"

api-venv-check:
	@test -x $(API_DIR)/$(VENV_BIN)/python || { echo "Missing $(API_DIR)/.venv — run: make install-api"; exit 1; }

test: test-api ## Run all test suites (web joins in M0-P4)

test-api: api-venv-check ## Run the API test suite (pytest)
	cd $(API_DIR) && $(VENV_BIN)/pytest -q

lint: api-venv-check ## Lint and format-check the API (ruff)
	cd $(API_DIR) && $(VENV_BIN)/ruff check . && $(VENV_BIN)/ruff format --check .

typecheck: api-venv-check ## Type-check the API (mypy)
	cd $(API_DIR) && $(VENV_BIN)/mypy
