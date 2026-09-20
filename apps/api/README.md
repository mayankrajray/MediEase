# apps/api — MediEase API and worker

Flask API (HTTP + webhooks) and the background worker, sharing one hexagonal Python package.
Architecture: `docs/ARCHITECTURE.md` §3. Rules for agents: `CLAUDE.md` in this folder.

## Status

Skeleton only. The package, `pyproject.toml`, Dockerfile and first endpoints are created in
Milestone 0 (see `docs/milestones/M0-foundation.md`).

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

## Commands (from M0)

Run from the repository root: `make test-api`, `make lint`, `make typecheck`, `make migrate`.
