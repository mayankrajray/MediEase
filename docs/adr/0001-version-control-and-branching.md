# ADR-0001: Git, GitHub and trunk-based development

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | CONTRIBUTING.md, CLAUDE.md "Git Workflow" |

## Context

A small team working with AI agents needs a history that is easy to read, easy to revert, and maps
to the milestone/phase plan. Long-lived branches create merge pain and hide broken states.

## Decision

- Git hosted on GitHub; `main` is always deployable.
- Short-lived branches per phase (`m<milestone>/p<phase>-<slug>`), merged by squash after green CI
  and one review.
- Conventional Commits with PRD requirement IDs.
- The developer owns history; agents never commit or push unless asked.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| GitFlow (develop/release branches) | Ceremony without benefit at our size; slows feedback |
| Direct commits to main | No review gate for health-data code |
| Merge commits (non-squash) | Noisy history; phases would not map to single commits |

## Consequences

- One commit per phase makes rollback and bisecting simple.
- Requires discipline to keep phases small enough to review.
- Revisit if we add a mobile app with independent release cadence.
