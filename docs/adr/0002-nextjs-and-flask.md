# ADR-0002: Next.js web app and Flask API as separate services

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | ARCHITECTURE.md §2–4, NFR-02, NFR-14 |

## Context

The team is fluent in Next.js, Flask, Docker and Git. The product needs a desktop-grade clinic
dashboard, very light mobile patient pages, an internal ops console, an HTTP API, webhook receivers
and a background worker that shares business logic with the API.

## Decision

- **Web:** Next.js (App Router, TypeScript) for all three UI surfaces, using route groups
  `(clinic)`, `(patient)`, `(ops)`. Server Components by default to keep patient pages light.
- **API:** Flask with an application factory as the composition root, Pydantic v2 for validation
  and settings, served by Gunicorn. The worker is a second entrypoint of the same Python package.
- Business logic lives only in the Python domain/application layers. The web app never contains
  business rules beyond presentation and input hints.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Next.js full-stack (API routes + ORM) | One language | Weaker fit for hexagonal domain + worker; team's backend strength is Python | Mixed concerns |
| FastAPI instead of Flask | Async, built-in OpenAPI | Team already knows Flask; async adds concepts we do not yet need | Familiarity and simplicity first |
| Django | Batteries included, admin | Heavier conventions pull against ports-and-adapters | Architectural fit |
| Spring Boot (used in a previous programme project) | Team has shipped it | Developer asked for Flask; slower iteration | Preference and speed |

## Consequences

- Two runtimes to build and deploy; mitigated by Docker Compose and one Makefile.
- The OpenAPI contract becomes essential to keep the two sides aligned (ADR-0008).
- Flask gives no OpenAPI generation for free; we write the contract first and test against it.
- Revisit if we need high-concurrency long-lived connections (e.g. SSE at scale).
