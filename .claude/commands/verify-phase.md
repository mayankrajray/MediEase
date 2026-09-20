---
description: Check a completed phase against the Definition of Done
argument-hint: <phase id>
---

Verify phase **$ARGUMENTS** against CLAUDE.md "Definition of Done". Report, do not fix.

1. Run `make lint`, `make typecheck`, `make test` and report results (commands that do not exist yet: say so).
2. For each acceptance criterion in the phase's spec, name the test that covers it, or mark it MISSING.
3. Confirm the documentation table in CLAUDE.md was honoured: `openapi.yaml`, `API.md`,
   `DATA_MODEL.md`, `ERRORS.md`, `.env.example`, `TASKS.md`, `CHANGELOG.md` — updated or not needed, with reason.
4. Check for: clinical content or unmasked phones in log calls; tenant queries without scope;
   `datetime.now()` without timezone; new dependencies without justification; dead code or TODOs.
5. Output a checklist with ✅ / ❌ and the Changed Files manifest from `git status`.
