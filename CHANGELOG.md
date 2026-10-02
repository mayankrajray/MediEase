# Changelog

All notable changes are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow milestones until the
first production release.

## [Unreleased]

### Added
- Planning pack: PRD, CLAUDE.md, AGENTS.md, TASKS.md, SPECS.md, architecture, data model, API
  design, debugging guide, error catalogue, runbook, security and compliance notes, ADR-0001 to
  ADR-0009, feature specs for M1–M5, and the repository skeleton.
- Local PostgreSQL service in `docker-compose.yml` and base `Makefile` targets (M0-P1).
- `NEXT_STEPS_PLAN.md`: approved M0 implementation plan with workflow prerequisites and progress log.
- ADR-0010: issue-driven workflow, one commit per logical change, rebase merges, CODEOWNERS approval.
- `.gitattributes`: LF line endings in the index and working tree on every platform (M0-P1).
- `.github/CODEOWNERS`: default owners for every path (M0-P1, W-6).
- API package `mediease_api` (M0-P2): `pyproject.toml` with pinned runtime and dev dependencies;
  typed `AppSettings` + `load_settings()` that fail fast on invalid config (`CFG_INVALID`, naming
  each rejected field); structlog JSON logging for app and framework records with `request_id`
  in contextvars; `X-Request-ID` middleware (safe inbound IDs echoed, otherwise a ULID; access log
  with route template and `duration_ms`); error envelope with `REQ_NOT_FOUND`,
  `REQ_METHOD_NOT_ALLOWED` and `SYS_UNEXPECTED`; `GET /health`; Flask app factory (`create_app`)
  and gunicorn `wsgi` entrypoint; 31 unit and integration tests.
- `Makefile` targets `install-api`, `test`, `test-api`, `lint`, `typecheck` (M0-P2).
- Database readiness (M0-P3): SQLAlchemy 2 engine (psycopg 3) behind a `DatabaseCheck` port;
  `GET /ready` runs `SELECT 1` within a 2-second budget and returns 200 or 503
  `READY_DB_UNAVAILABLE` / `READY_DB_TIMEOUT`; `ready.check_failed` warning log.
- Alembic with an empty baseline revision `0001`; `migrations/env.py` reads the settings (M0-P3).
- Minimal non-root API `Dockerfile` (`python:3.12.15-slim-trixie`, gunicorn `--preload`) (M0-P3).
- Compose `migrate` (one-off `alembic upgrade head`) and `api` (healthcheck `/ready`) services;
  `make up` builds and starts db → migrate → api; `make migrate` (M0-P3).
- Contract tests validating `/health` and `/ready` against `contracts/openapi.yaml`; real-PostgreSQL
  integration tests for readiness and migrations; 55 tests in total (M0-P3).

### Verified
- M0-P1 closed: `db` starts healthy, `select 1` returns 1 in UTC, `down` keeps `pgdata`, and an
  empty `POSTGRES_PASSWORD` is refused before any container starts (#6).

### Changed
- `DATABASE_URL` must use the `postgresql+psycopg://` scheme; anything else fails start-up with
  `CFG_INVALID` (M0-P3).
- `CLAUDE.md`: new "Commit Standards"; "Git Workflow" now issue → branch → PR with no direct pushes
  to `main`, pushes only with permission and merges only by authorised maintainers; Docker start-up
  order declared with `depends_on` (`api` waits for `migrate`).
- `AGENTS.md`, `CONTRIBUTING.md`, PR template, `TASKS.md`, M0 design notes updated to match.
- M0-P3 now includes a minimal API `Dockerfile` so the `migrate` service can run before P5.
