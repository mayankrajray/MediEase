# ADR-0011: One branch and one pull request per milestone

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-02 |
| Deciders | Developer (project owner) |
| Related | ADR-0010 (superseded in part), CLAUDE.md "Git Workflow", CONTRIBUTING.md, TASKS.md |

## Context

ADR-0010 tied one issue, one branch and one PR to each phase. M0 produced six PRs for five small
phases, plus the review and merge overhead for each. The developer wants a milestone reviewed and
merged as one unit, while keeping the phase-by-phase design, testing and confirmation gates and
the per-change commit history.

## Decision

- **One milestone, one issue, one branch, one PR.** The milestone issue lists every phase as a
  checklist and is the `Refs`/`Closes` target for all commits in the milestone.
- **Branch name:** `m<milestone>/<issue#>-<slug>`, e.g. `m1/19-identity-tenancy-audit`, created
  from the latest `origin/main` when the milestone starts.
- **Phases stay the unit of work.** Each phase is designed, approved, implemented, verified and
  confirmed by the developer before the next one starts. Its commits are pushed to the milestone
  branch (with the developer's permission), so the PR grows phase by phase.
- **The PR is opened as a draft** after the first phase is pushed and marked ready for review only
  when every phase is done and the milestone exit criteria are met. CI runs on every push.
- **Commit subjects name the phase in the body or scope where it helps review**; the footer is
  `Refs #<milestone issue>`, and the final commit of the milestone carries `Closes #<issue>`.
- **Only one milestone is open at a time.** The next milestone's branch is created after the
  previous milestone's PR is merged.

Unchanged from ADR-0010: one commit per logical change with a body and footer; every commit builds
and passes tests; rebase and merge; no direct pushes to `main`; agents push only with permission
and never merge; CODEOWNERS approval where the repository enforces it.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Keep one PR per phase (ADR-0010) | Small reviews; `main` gets each phase early | Many PRs and merges per milestone; phase PRs depend on each other | Developer wants one review and merge per milestone |
| Stacked phase PRs on a milestone branch | Small reviews and one milestone merge | Rebase churn across stacked PRs; tooling overhead | More ceremony than benefit for a small team |
| One squash commit per milestone | Very short history | Loses logical commits; hard to bisect | Conflicts with the commit standards |

## Consequences

- Positive: one review and one merge per milestone; the PR shows the milestone as a whole;
  phase commits remain individually reviewable and revertible.
- Negative / costs: the milestone PR is large, so commits must stay clean and logical and the PR
  description must summarise each phase; `main` only receives a milestone when it is complete.
  Long-lived branches can drift from `main`: rebase onto `origin/main` only with the developer's
  approval (CLAUDE.md "No history rewriting on shared branches").
- Follow-ups and triggers to revisit: if a milestone PR becomes too large to review, split the
  review by phase commit ranges, or revisit this ADR.
