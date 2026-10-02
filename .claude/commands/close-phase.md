---
description: Prepare the hand-off for a phase the developer has tested
argument-hint: <phase id>
---

Close phase **$ARGUMENTS** (only after I confirm I tested it):

1. Update `TASKS.md`: mark the phase ✅, set the next phase `▶ ACTIVE`, update "Current focus".
2. Add the change to `CHANGELOG.md` under Unreleased.
3. Update `NEXT_STEPS_PLAN.md`: task state and a row in the progress log (issue, PR, date).
4. Output:
   - Summary with requirement IDs
   - Changed Files manifest (added / modified / deleted)
   - Verification steps that were run
   - The logical commits on the task branch (subject + body, per CLAUDE.md "Commit Standards")
5. Commit only on the task branch. Push to that branch and open the PR only if I explicitly permit
   it now. Never push to `main` and never merge.
