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
- M1-P2 (#19): sign-in by email or phone (FR-AUTH-01) with Argon2id hashing (argon2-cffi 25.1.0),
  constant-time handling of unknown accounts, and lockout for 15 minutes after 5 consecutive
  failures (FR-AUTH-04, `AUTH_LOCKED` 423 with `Retry-After`).
- M1-P2: sessions (FR-AUTH-02): 15-minute HS256 access JWT (PyJWT 2.15.1) and 14-day rotating
  refresh token stored as SHA-256; replaying a rotated token revokes the whole family
  (`AUTH_REFRESH_REUSED`); sign-out revokes the family. `POST /api/v1/auth/sign-in`, `/refresh`,
  `/sign-out` in `contracts/openapi.yaml` 0.2.0.
- M1-P2: `HttpOnly` path-scoped cookies `me_access`, `me_refresh` and a `me_csrf` double-submit
  token checked on every unsafe `/api/*` request with session cookies (`AUTH_CSRF_INVALID`).
- M1-P2: migration `0003` (users credentials and lockout; `refresh_tokens`); clock port; request
  validation with `REQ_VALIDATION_FAILED` / `details.fields`; domain error → HTTP status mapping.
- M1-P2: settings `JWT_SIGNING_KEY` (≥ 32 characters, required), `ACCESS_TOKEN_TTL_SECONDS`,
  `REFRESH_TOKEN_TTL_SECONDS`; `make seed` with synthetic local demo users; RUNBOOK §17
  (locked-out account).
- M1-P3 (#19): authorisation on every route (FR-AUTH-03). Each route declares an access policy
  (`@public`, `@authenticated`, `@clinic(Permission.X)`, `@ops`) and one `before_request` hook
  enforces it; `create_app` refuses to start if any route has none, and an undeclared route is
  refused rather than served (default deny).
- M1-P3: the PRD §8.1 permission matrix as domain data (`Permission`, `ROLE_PERMISSIONS`,
  `permissions_for`); an owner with a linked doctor profile also gets `CLINICAL_WRITE`.
- M1-P3: every request re-reads the session, the user and the membership (R7), so sign-out ends
  access at once (`AUTH_SESSION_EXPIRED`) and a deactivated member or disabled user is refused on
  their next request (`AUTH_ACCOUNT_DISABLED`, AC4). New reads
  `RefreshTokenRepository.is_family_live` and `MembershipRepository.list_staff`.
- M1-P3: clinic resolution (R6) from the single membership or `X-Clinic-ID`; ambiguous, malformed
  and foreign values all answer `PERM_CLINIC_REQUIRED` (400). New codes `PERM_DENIED` (403),
  `PERM_CLINIC_REQUIRED` (400) and `CLN_SUSPENDED` (403); ops users are refused on clinic routes
  and clinic staff on ops routes (R10).
- M1-P3: `GET /api/v1/me` (user, memberships with clinic status, role and permissions) and
  read-only `GET /api/v1/clinic`, `/clinic/doctors`, `/clinic/doctors/{doctor_id}`,
  `/clinic/staff` in `contracts/openapi.yaml` 0.3.0 with the `X-Clinic-ID` parameter and a
  `me_access` cookie security scheme; sign-in and refresh bodies now carry the same membership
  shape. Lists return `{"items": [...]}` and are unpaginated by design at this size.
- M1-P3: HTTP tenancy suite (`tests/tenancy/test_http_isolation.py`) proving AC3 end to end, with
  a guard that fails when a new clinic route taking a resource ID has no cross-clinic case.

### Upgrade notes
- M1-P2: existing local `.env` files need `JWT_SIGNING_KEY` of at least 32 characters (copy the
  line from `.env.example`); otherwise `make up` stops with `CFG_INVALID`.
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
