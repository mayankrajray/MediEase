# CLAUDE.md — apps/api

Loaded in addition to the root `CLAUDE.md` when working in this folder.

## Layer rules (enforced by an import-boundary check from M0-P5)
- `domain/` imports only the standard library. No Flask, SQLAlchemy, Pydantic, requests.
- `application/` imports `domain/` and `ports/` only. Use cases receive ports via `__init__`.
- Only `bootstrap.py` chooses adapters. Nothing else instantiates an adapter.
- `delivery/` translates HTTP ↔ commands/views and domain errors ↔ error envelopes. No business rules.

## Patterns
- One use case per user action: `class BookAppointment: def execute(self, ctx, cmd) -> View`.
- `RequestContext(request_id, clinic_id, user_id, role)` is passed explicitly; do not use Flask `g`
  inside application code.
- The unit of work wraps each command: scoped repositories, audit writer and job enqueuer share one
  transaction.
- Domain errors carry a stable `code`; the mapping to HTTP status lives in `delivery/errors.py`.
- Time comes from `ClockPort`; IDs from `IdPort` (UUIDv7).
- Pydantic models live at the boundary (request/response, settings), not in the domain.

## Database
- Every tenant table has `clinic_id`; every tenant query goes through a scoped repository.
- Booking and other capacity checks lock the parent row with `SELECT … FOR UPDATE`.
- Migrations are expand → migrate → contract; never edit a migration that has run anywhere shared.
- Update `docs/DATA_MODEL.md` with every migration.

## Logging
- `log.info("appointment.booked", appointment_id=..., source=...)` — event names are
  `area.past_tense`; fields are IDs and enums.
- Phones are masked with the shared helper; names and clinical text are never logged.

## Tests
- Name tests after requirements: `test_fr_apt_04_...`.
- Unit tests use in-memory fakes of ports; integration tests use the real PostgreSQL service.
- Every new tenant resource adds cases to `tests/tenancy/`.
