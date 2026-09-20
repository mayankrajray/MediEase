# ADR-0003: Shared-schema multi-tenancy with scoped repositories

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | NFR-08, FR-AUTH-03, ARCHITECTURE.md §6 |

## Context

Every clinic's patient data must be isolated from every other clinic. We expect tens of clinics
in the pilot year, each small. Operational simplicity matters: one team, one database.

## Decision

- One PostgreSQL database and schema. Every tenant-owned table has `clinic_id NOT NULL`.
- The unit of work constructs repositories bound to the request's `clinic_id`; repository methods
  cannot accept another clinic ID. There is no unscoped tenant repository in application code.
- Platform-level operations use separately named repositories that never expose clinical columns.
- Cross-tenant requests return 404.
- A permanent tenancy test suite covers every endpoint.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Database per clinic | Strongest isolation | Migrations × N, connection sprawl, ops burden | Too heavy for pilot scale |
| Schema per clinic | Good isolation | Migration fan-out, search_path mistakes | Complexity without matching benefit now |
| Row-Level Security only | Enforced in the database | Harder to debug; session variable mistakes fail open if misconfigured | Planned as a *second* layer, not the only one |

## Consequences

- Isolation depends on code discipline, backed by tests and review.
- Composite indexes must lead with `clinic_id`.
- **Follow-up:** enable PostgreSQL RLS policies as defence in depth after the pilot, with an ADR
  describing how the app sets the tenant context per transaction.
