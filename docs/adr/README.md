# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [0001](0001-version-control-and-branching.md) | Git, GitHub and trunk-based development | Accepted; merge and commit rules superseded by ADR-0010 |
| [0002](0002-nextjs-and-flask.md) | Next.js web app and Flask API as separate services | Accepted |
| [0003](0003-multi-tenancy.md) | Shared-schema multi-tenancy with scoped repositories | Accepted |
| [0004](0004-postgresql-sqlalchemy-alembic.md) | PostgreSQL with SQLAlchemy 2.x and Alembic | Accepted |
| [0005](0005-postgres-backed-job-queue.md) | PostgreSQL-backed job queue before a message broker | Accepted |
| [0006](0006-authentication-and-same-origin-api.md) | Cookie-based JWT sessions through a same-origin API proxy | Accepted |
| [0007](0007-messaging-port-whatsapp-first.md) | WhatsApp-first messaging behind a provider-agnostic port | Accepted |
| [0008](0008-contract-first-openapi.md) | Contract-first API with OpenAPI and generated web types | Accepted |
| [0009](0009-deployment-and-environments.md) | Docker everywhere; single India region for the pilot | Accepted |
| [0010](0010-issue-driven-workflow-and-logical-commits.md) | Issue-driven workflow with logical commits and rebase merges | Accepted |

New ADR: copy [0000-template.md](0000-template.md), take the next number, and add a row here.
Accepted ADRs are never edited; supersede them with a new ADR.
