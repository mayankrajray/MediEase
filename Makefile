# MediEase developer commands. Every target is documented in AGENTS.md §4.
# Targets for later milestones are added in the milestone that needs them.

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help env-check up down ps logs psql

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
