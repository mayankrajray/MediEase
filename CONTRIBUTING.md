# Contributing to MediEase

## Workflow

1. Pick the active phase in [TASKS.md](TASKS.md). Do not start another.
2. Make sure its spec in `docs/specs/` is `Approved`. If not, get it approved first.
3. Create a branch: `m<milestone>/p<phase>-<slug>` — e.g. `m3/p2-booking-locking`.
4. Write the design note (what, why, where, which files) and get approval.
5. Implement in small commits locally; squash to **one commit per completed phase**.
6. Run `make lint typecheck test` — all must pass.
7. Update the documents listed in CLAUDE.md → "Documentation That Makes Debugging Possible".
8. Open a PR using the template. CI must be green. One approving review before merge.
9. Merge with squash to `main`. Update `TASKS.md` and `CHANGELOG.md`.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) with requirement IDs:

```
feat(prescriptions): add dilution instructions to Rx items (FR-RX-02)
fix(queue): reject COMPLETED → ARRIVED transition (FR-QUE-02)
docs(errors): document APT_SLOT_TAKEN
chore(ci): cache pip dependencies
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`.

## Branch protection (configure on GitHub)

- `main` requires a PR, green CI and one approval.
- No force pushes, no direct commits.
- Linear history (squash merges).

## Using AI agents

Agents follow [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md). The human who opens the PR is
responsible for every line in it: read the diff, run the verification steps, and be able to explain
the design. AI-generated code gets the same review as human code.

## Data rules

Never use real patient data, real phone numbers or real clinic names anywhere in the repository,
issues, PRs or AI prompts. Use `scripts/` generators for fixtures.
