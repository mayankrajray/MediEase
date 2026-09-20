# ADR-0009: Docker everywhere; single India region for the pilot

| Field | Value |
|---|---|
| Status | Accepted (deployment target to be confirmed in M6) |
| Date | 2026-09-15 |
| Related | NFR-03..07, NFR-15, ARCHITECTURE.md §11, TASKS L-05 |

## Context

Health data should stay in India, costs must stay low at pilot scale, and the team knows Docker.
We need backups and point-in-time recovery without running our own database operations.

## Decision

- Every service is a container built in CI and tagged with the commit SHA.
- Local: Docker Compose, one command (`make up`).
- Pilot: containers on a single India-region compute host (or a simple container service), a
  **managed PostgreSQL** in the same region with automated backups and PITR, and S3-compatible
  object storage in the same region. A reverse proxy terminates TLS.
- Environments: local, staging (synthetic data only), production.
- The concrete provider is chosen in M6 against: India region, managed Postgres with PITR, cost,
  and team familiarity; recorded in a follow-up ADR.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Kubernetes | Operational overhead far beyond pilot needs |
| Serverless functions | Worker and long-lived polling fit poorly; local parity suffers |
| Self-managed PostgreSQL on the VM | Backups/PITR become our problem |

## Consequences

- Simple, cheap, reproducible; limited horizontal scaling (acceptable for the pilot).
- Revisit for multi-host deployment when a single host cannot meet NFR-01 or NFR-03.
