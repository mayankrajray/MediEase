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
| [0010](0010-issue-driven-workflow-and-logical-commits.md) | Issue-driven workflow with logical commits and rebase merges | Accepted; per-phase issue/branch/PR superseded by ADR-0011 |
| [0011](0011-one-branch-and-pr-per-milestone.md) | One branch and one pull request per milestone | Accepted |
| [0012](0012-in-house-pdf-rendering-and-blob-storage.md) | In-house PDF rendering and blob storage behind ports | Accepted |
| [0013](0013-llm-gateway.md) | An LLM gateway behind a port, OpenAI-compatible, Groq first | Accepted |
| [0014](0014-multi-clinic-whatsapp-and-consolidated-billing.md) | Each clinic's own WhatsApp number, and one consolidated MediEase invoice | Proposed (built in M8) |
| [0015](0015-patient-accounts-and-google-sign-in.md) | Patient accounts apart from staff, and Google sign-in through the API | Accepted (M6a-P3) |
| [0016](0016-email-port-smtp-and-auth-emails.md) | Email behind a port, sent over SMTP from the job queue | Accepted (M6a-P4) |
| [0017](0017-notification-service.md) | Domain events and a notification service, dispatched in the publishing transaction | Accepted (M6a-P7) |
| [0018](0018-soft-hold-as-booking-request.md) | The soft hold is the pending booking request, counted under the session lock | Accepted |

New ADR: copy [0000-template.md](0000-template.md), take the next number, and add a row here.
Accepted ADRs are never edited; supersede them with a new ADR.
