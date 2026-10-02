## Pull request process

- Issue: Closes #
- Branch: `m<milestone>/<issue#>-<slug>` (one milestone, one issue, one branch, one PR — every phase of the milestone, nothing else; ADR-0011)
- Draft until every phase is done and the milestone exit criteria are met
- Target: `main` via review only; merged with **rebase and merge** by an authorised maintainer after CODEOWNERS approval

## Milestone and phases

<!-- e.g. M3 — Appointments and daily queue. Tick each phase when the developer has confirmed it. -->

- [ ] P1 —

## Commits

<!-- One commit per logical change, grouped by phase. List each subject; every commit has a body (what + why) and "Refs #<issue>". -->

-

## Requirements

<!-- FR-/NFR- IDs this PR satisfies -->

## What and why

## Changed files

- Added:
- Modified:
- Deleted:

## How to verify

1.
2.
3. Failure path:

## Checklist

- [ ] Spec is `Approved` and acceptance criteria have tests
- [ ] `make lint typecheck test` passes locally
- [ ] Tenancy isolation covered for any new tenant resource
- [ ] No clinical content or unmasked phone numbers in logs, messages or analytics
- [ ] Docs updated: openapi.yaml / API.md / DATA_MODEL.md / ERRORS.md / .env.example / RUNBOOK.md (as applicable)
- [ ] Migration is backward compatible (or rollback plan described)
- [ ] `TASKS.md` and `CHANGELOG.md` updated
- [ ] I can explain every line of this diff (including AI-generated code)
- [ ] Each logical change is a separate commit with an imperative subject, a body and `Refs #<issue>`
- [ ] This PR contains only the linked milestone's changes
- [ ] `NEXT_STEPS_PLAN.md` updated if scope, order or approach changed
