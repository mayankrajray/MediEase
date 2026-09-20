# ADR-0004: PostgreSQL with SQLAlchemy 2.x and Alembic

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | DATA_MODEL.md, CLAUDE.md "Docker / Service Architecture" |

## Context

We need relational integrity (appointments, sessions, prescriptions), row-level locking for
booking, JSON for a few variable shapes, reliable backups and managed hosting in India.

## Decision

- PostgreSQL 16.
- SQLAlchemy 2.x with typed ORM models confined to the adapters layer; domain entities are plain
  Python classes mapped by repositories.
- Alembic for migrations, run by a one-off `migrate` container before the app starts.
- UUIDv7 primary keys; `timestamptz` everywhere; enums as `text` + `CHECK`.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| MySQL | Weaker `SKIP LOCKED`/partial index ergonomics for our job table and booking constraints |
| MongoDB | Relational integrity is central to the domain |
| Flask-SQLAlchemy / Flask-Migrate | Couples models to the Flask app object; plain SQLAlchemy keeps the core framework-free |
| Raw SQL only | More boilerplate; fewer safety rails for a small team |

## Consequences

- Mapping between ORM models and domain entities is extra code, accepted for testability.
- Migrations must be backward compatible with the previous app version (expand → migrate → contract).
