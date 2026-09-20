# ADR-0005: PostgreSQL-backed job queue before a message broker

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | FR-REM, FR-MSG, NFR-13, ARCHITECTURE.md §7 |

## Context

We need delayed and retried background work: reminders at specific times, message sends, PDF
rendering, webhook reconciliation. Pilot volume is small (hundreds of jobs per day). Jobs must be
created atomically with the business change that causes them, and must never send a patient
message twice.

## Decision

- A `jobs` table in the main database, inserted in the same transaction as the triggering change
  (transactional outbox).
- A separate `worker` process claims due jobs with `SELECT … FOR UPDATE SKIP LOCKED`, runs the
  handler, and records the outcome. Exponential backoff with jitter; `dead` after `max_attempts`.
- Stale locks (> 5 minutes) are reclaimed by a reaper loop.
- Handlers are idempotent; outbound messages carry an idempotency key.
- Access is through `JobQueuePort`, so the implementation can be swapped.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Redis + RQ / Celery | Mature, fast | New service to run and secure; no atomic enqueue with DB writes without an outbox anyway | Not yet justified (Infrastructure Philosophy) |
| Cron + scripts | Simple | No retries, no idempotency, poor observability | Unsafe for patient messaging |
| Cloud scheduler/queue | Managed | Cloud lock-in; harder local parity | Local reproducibility (NFR-15) |

## Consequences

- One fewer service; jobs are inspectable with SQL.
- Polling adds light database load; acceptable at pilot scale.
- **Revisit when:** sustained > 50 jobs/s, claim latency > 1 s, or job table bloat affects the
  primary workload.
