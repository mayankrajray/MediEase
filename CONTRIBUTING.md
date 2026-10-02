# Contributing to MediEase

## Workflow

Every milestone follows: **milestone issue → milestone branch → phase by phase (design → approval
→ logical commits → developer confirms → push) → one PR per milestone → review/CODEOWNERS
approval → merge by an authorised maintainer** (ADR-0010, ADR-0011).

1. Pick the active milestone and phase in [TASKS.md](TASKS.md) and the matching plan in
   [NEXT_STEPS_PLAN.md](NEXT_STEPS_PLAN.md). Do not start another.
2. Make sure its spec in `docs/specs/` is `Approved`. If not, get it approved first.
3. When a milestone starts, open **one issue** for it, listing every phase as a checklist.
4. Create **one branch** for the milestone from the latest `origin/main`:
   `m<milestone>/<issue#>-<slug>` — e.g. `m3/41-appointments-and-queue`. Every phase of the
   milestone is committed to this branch.
5. For each phase: write the design note (what, why, where, which files) and get approval.
6. Implement as **one commit per logical change** (see below). Every commit builds and passes tests.
7. Run `make lint typecheck test` — all must pass.
8. Update the documents listed in CLAUDE.md → "Documentation That Makes Debugging Possible",
   including `NEXT_STEPS_PLAN.md` if scope or approach changed.
9. Push **only the milestone branch** (agents: only with the developer's explicit permission).
   After the first phase, open the milestone PR **as a draft** using the template, linking the
   issue; later phases are pushed to the same PR.
10. When every phase is done and the exit criteria are met, mark the PR ready for review. CI must
    be green; one approving review and CODEOWNERS approval are required.
11. An authorised maintainer merges with **rebase and merge**. Then update `TASKS.md` and
    `CHANGELOG.md` and start the next milestone from the new `origin/main`.

**Never push directly to `origin/main`, and never merge a PR without the required approvals.**

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) with requirement IDs. Each commit has:

- A subject in imperative mood, ≤ 72 characters, no trailing period.
- A blank line, then a body wrapped at 72 characters explaining what changed and why.
- A footer `Refs #<issue>` with the milestone issue (`Closes #<issue>` on the final commit of the
  milestone).

```
feat(prescriptions): add dilution instructions to Rx items (FR-RX-02)

Homoeopathy clinics prescribe dilutions that the free-text dose field
could not express consistently. Items now carry an optional dilution
value validated against the clinic's own history; no external drug data
is used.

Refs #57
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`, `build`, `ci`.
Full rules: CLAUDE.md → "Commit Standards".

## Branch protection (configure on GitHub)

- `main` requires a PR, green CI checks, one approval and **CODEOWNERS review**
  (`.github/CODEOWNERS`).
- No direct pushes and no force pushes to `main`, including for administrators.
- Linear history; **rebase merging** enabled (squash and merge commits disabled), so logical
  commits are preserved.

## Using AI agents

Agents follow [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md). They may create issues, branches
and commits for the active milestone, push to that milestone's branch and open or update its PR
only with the developer's explicit permission, and never merge. The human who owns the PR is responsible for
every line in it: read the diff, run the verification steps, and be able to explain the design.
AI-generated code gets the same review as human code.

## Data rules

Never use real patient data, real phone numbers or real clinic names anywhere in the repository,
issues, PRs or AI prompts. Use `scripts/` generators for fixtures.
