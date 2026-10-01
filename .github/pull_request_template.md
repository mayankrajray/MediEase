## Pull request process

- Issue: Closes #
- Branch: `m<milestone>/p<phase>-<issue#>-<slug>` (one issue, one branch, one PR — no unrelated changes)
- Target: `main` via review only; merged with **rebase and merge** by an authorised maintainer after CODEOWNERS approval

## Commits

<!-- One commit per logical change. List each subject; every commit has a body (what + why) and "Refs #<issue>". -->

-

## Phase

<!-- e.g. M3-P2 — Booking with row-level locking -->

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
- [ ] This PR contains only the linked issue's changes
- [ ] `NEXT_STEPS_PLAN.md` updated if scope, order or approach changed
