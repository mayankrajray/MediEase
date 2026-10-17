# apps/api — MediEase API and worker

Flask API (HTTP + webhooks) and the background worker, sharing one hexagonal Python package.
Architecture: `docs/ARCHITECTURE.md` §3. Rules for agents: `CLAUDE.md` in this folder.

## Status

M0: package, typed settings, structured logging, request IDs, error envelope, `GET /health`,
`GET /ready` (database check), Alembic, and hardened images for the compose `migrate` and `api`
services (see `docs/milestones/M0-foundation.md`).

M1-P1: domain model (clinics, doctors, users, memberships), ID / repository / unit-of-work ports,
UUIDv7 IDs, migration `0002`, tenancy-scoped SQLAlchemy repositories and unit of work (see
`docs/milestones/M1-identity-tenancy-audit.md`).

M1-P2: sign-in, refresh rotation with reuse detection, sign-out and lockout
(`/api/v1/auth/*`), Argon2id and JWT adapters, CSRF double submit, migration `0003`, and
`make seed` (synthetic demo users, local only).

M1-P3: authorisation on every route (access policy, default deny), per-request re-check of
session/user/membership, clinic resolution, permission matrix, `GET /api/v1/me` and read-only
clinic endpoints.

M1-P4: append-only `audit_events` (migration `0004`) with database-enforced immutability
(triggers), `v_clinic_activity`, audited staff role change.

M1-P5: ops onboarding (`POST /api/v1/ops/clinics`, doctors, staff invites), single-use
invitations and acceptance, owner staff and doctor management, migration `0005` (invitation
columns, `onboarding_checklists`).

M1-P6: web sign-in, clinic switcher, dashboard shell (merged; see M1 notes).

M1-P7: web ops console with Create clinic wizard (merged; see M1 notes).

M2-P1: patient domain, clinic code allocation, migration `0006`, tenancy-scoped repository,
lookup indexes, 10,000-patient performance test.

M2-P2: register/edit/lookup endpoints, duplicate-phone flow with candidates, audit without
personal data, clinic-local ages, `patient_code_prefix`, contract 0.6.0.

M2-P3: consent recording, opt-out and opt-in as separate actions, row lock, audit as evidence,
`whatsapp_allowed`/`sms_allowed`, contract 0.7.0.

M2-P4: ops CSV patient import (`POST /api/v1/ops/clinics/{id}/patient-imports`), dry run by
default, batched inserts, contract 0.8.0.

## Layout

| Path | Layer | May import |
|---|---|---|
| `src/mediease_api/domain/` | Entities, value objects, state machines, domain errors | standard library only |
| `src/mediease_api/application/` | Use cases and job handlers | `domain`, `ports` |
| `src/mediease_api/ports/` | Interfaces (Protocols) | `domain` |
| `src/mediease_api/adapters/` | SQLAlchemy, messaging, storage, PDF, clock | anything inward + libraries |
| `src/mediease_api/delivery/` | Flask blueprints, webhooks, worker entrypoint, middleware | anything inward |
| `src/mediease_api/config/` | Typed settings and logging | libraries |
| `src/mediease_api/bootstrap.py` | Composition root (M0-P2) | everything |
| `migrations/` | Alembic (M0-P3) | adapters' models |
| `tests/` | unit, integration, tenancy, contract | everything |

## Commands

Run from the repository root inside WSL (or Linux/macOS) with Python 3.12 on `PATH`:

```bash
make up                     # db -> migrate -> api in containers; API on localhost:8000
make install-api            # creates apps/api/.venv and installs the package + dev tools
make lint typecheck test    # ruff, mypy, pytest (integration tests use the compose db)
make migrate                # re-run migrations (make up already ran them)
```

To run the API outside a container, point `DATABASE_URL` at `localhost` instead of `db`:

```bash
cd apps/api
set -a && source ../../.env && set +a
export DATABASE_URL="${DATABASE_URL/@db:/@localhost:}"
.venv/bin/gunicorn --bind 127.0.0.1:8001 mediease_api.wsgi:app
curl -i localhost:8001/ready
```
