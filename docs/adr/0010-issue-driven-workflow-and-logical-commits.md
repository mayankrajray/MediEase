# ADR-0010: Issue-driven workflow with logical commits and rebase merges

| Field | Value |
|---|---|
| Status | Accepted — one issue/branch/PR per phase and the branch name superseded by [ADR-0011](0011-one-branch-and-pr-per-milestone.md) |
| Date | 2026-10-01 |
| Deciders | Developer (project owner) |
| Related | ADR-0001 (superseded in part), CLAUDE.md "Git Workflow" and "Commit Standards", CONTRIBUTING.md, NEXT_STEPS_PLAN.md §3 |

## Context

ADR-0001 chose short-lived phase branches, squash merges and one commit per phase. With AI agents
creating branches, commits and PRs, the developer wants finer traceability: every task tracked by
an issue, every logical change reviewable and revertible on its own, and a hard guarantee that
nothing reaches `main` without review and CODEOWNERS approval.

## Decision

- **Issue first.** Every logical task has one issue, one branch and one PR. Unrelated work is never
  combined.
- **Branch name:** `m<milestone>/p<phase>-<issue#>-<slug>`.
- **One commit per logical change**, each with an imperative Conventional Commits subject, a body
  explaining what and why, and `Refs #<issue>`. Every commit builds and passes tests.
- **Rebase and merge** replaces squash merges so logical commits survive on `main` while history
  stays linear.
- **No direct pushes to `main`.** Agents push only to the task branch, and only with the
  developer's explicit permission. Agents never merge.
- **CODEOWNERS approval** is required on `main` through branch protection.

This supersedes ADR-0001's "merged by squash" and "one commit per phase" rules. The rest of
ADR-0001 (GitHub, trunk-based development, `main` always deployable, Conventional Commits with
requirement IDs) still applies.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Keep squash merge + one commit per phase (ADR-0001) | Very simple history | Loses logical steps; large phase commits are hard to review and bisect | Developer requires per-change commits |
| Merge commits | Preserves commits | Non-linear history; conflicts with linear-history protection | Linear history kept |
| Issues optional for small changes | Less ceremony | Untracked work; agents may bundle unrelated changes | Consistency for every task |

## Consequences

- Positive: each change is reviewable, revertible and bisectable; issues give an audit trail from
  requirement to merge.
- Negative / costs: more commits and issues to manage; contributors must keep commits clean
  before review (fixup commits are tidied locally before the first push).
- Follow-ups: configure branch protection (rebase merge only, linear history, CODEOWNERS review,
  no direct or force pushes); add `.github/CODEOWNERS` (NEXT_STEPS_PLAN.md Task 1).
