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
- `docs/specs/identity-and-tenancy.md` Approved; M1 plan (`NEXT_STEPS_PLAN.md`) and design notes
  (`docs/milestones/M1-identity-tenancy-audit.md`); M1-P1 active (#19).
- M1-P1 (#19): domain model — `Clinic` (`ONBOARDING → ACTIVE ↔ SUSPENDED`, I1), `Doctor` (I3),
  `User`, `ClinicMembership` with roles and the last-owner rule (R9); `PhoneNumber` (E.164,
  masked) and `EmailAddress` value objects; domain codes `CLN_OWNER_REQUIRED`,
  `CLN_INVALID_TRANSITION`.
- M1-P1: `IdPort` with a UUIDv7 generator; repository and unit-of-work ports.
- M1-P1: migration `0002` (`clinics`, `users`, `clinic_memberships`, `doctors`); SQLAlchemy models,
  `TenantScopedRepository`, repositories and unit of work; permanent tenancy suite in
  `tests/tenancy/`; models-vs-migrations drift test.
- M1-P1: coverage gate ≥ 80% on `domain/` + `application/` in `make test-api` and CI (NFR-14).
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
- Web app (M0-P4): Next.js 16 App Router project in `apps/web` (TypeScript strict, ESLint, Tailwind 4),
  exact versions in `package-lock.json`, Node 24.21.0 in `.nvmrc`.
- API types generated from `contracts/openapi.yaml` (`npm run gen:api`, `make contract`) with a
  drift gate (`make contract-check`, CI) (M0-P4).
- Web API client `src/lib/api/client.ts`: `X-Request-ID` on every call, 5 s timeout, typed
  `ApiError`; web-side codes `WEB_API_UNREACHABLE` and `WEB_API_BAD_RESPONSE` (M0-P4).
- Same-origin proxy: `/api/*`, `/health`, `/ready` rewritten to `API_INTERNAL_URL` (ADR-0006);
  security headers with a per-request nonce CSP (M0-P4).
- `/status` page: healthy, degraded and API-down states, each with "Ref: <request_id>" (M0-P4).
- `make install-web`, `test-web`, `dev-web`; `make lint typecheck test` cover API and web; CI web
  job enabled with Node from `.nvmrc` (M0-P4).
- Container images (M0-P5): multi-stage, non-root API and web images with digest-pinned bases,
  Debian security updates applied and package managers removed from the runtime stage; web
  liveness route `/livez`.
- Full compose stack (M0-P5): `web` service after `api` is healthy; `migrate`, `api` and `web` run
  with a read-only root filesystem, no capabilities and `no-new-privileges`. `make smoke`
  (`scripts/smoke.sh`) checks the running stack, including those properties.
- CI gates (M0-P5): image build + Trivy scan, fresh-clone smoke test, gitleaks secrets scan,
  `pip-audit`, `npm audit`, import-linter layer contracts, API coverage gate ≥ 90%; `make audit`.
- Dependabot for pip (`apps/api`), npm (`apps/web`) and Docker base images (M0-P5).

### Verified
- M0-P1 closed: `db` starts healthy, `select 1` returns 1 in UTC, `down` keeps `pgdata`, and an
  empty `POSTGRES_PASSWORD` is refused before any container starts (#6).
- **M0 — Foundation closed** (#14): a fresh clone with an empty volume runs
  `cp .env.example .env && make up` to `db`, `api`, `web` healthy and `migrate` exited 0 in 77 s;
  `make smoke` passes; CI is green on the PR.

### Changed
- Workflow (ADR-0011): one issue, one branch (`m<milestone>/<issue#>-<slug>`) and one PR per
  milestone; every phase is committed to the milestone branch and the PR stays a draft until the
  milestone is done. Supersedes ADR-0010's per-phase issue, branch and PR. `CLAUDE.md`,
  `AGENTS.md`, `CONTRIBUTING.md`, the PR template and `/close-phase` updated.
- `DATABASE_URL` must use the `postgresql+psycopg://` scheme; anything else fails start-up with
  `CFG_INVALID` (M0-P3).
- `CLAUDE.md`: new "Commit Standards"; "Git Workflow" now issue → branch → PR with no direct pushes
  to `main`, pushes only with permission and merges only by authorised maintainers; Docker start-up
  order declared with `depends_on` (`api` waits for `migrate`).
- `AGENTS.md`, `CONTRIBUTING.md`, PR template, `TASKS.md`, M0 design notes updated to match.
- M0-P3 now includes a minimal API `Dockerfile` so the `migrate` service can run before P5.
