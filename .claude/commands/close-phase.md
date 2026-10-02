---
description: Prepare the hand-off for a phase the developer has tested
argument-hint: <phase id>
---

Close phase **$ARGUMENTS** (only after I confirm I tested it):

1. Update `TASKS.md`: mark the phase ✅, set the next phase `▶ ACTIVE`, update "Current focus".
2. Add the change to `CHANGELOG.md` under Unreleased.
3. Update `NEXT_STEPS_PLAN.md`: phase state and a row in the progress log (milestone issue, date).
4. Output:
   - Summary with requirement IDs
   - Changed Files manifest (added / modified / deleted)
   - Verification steps that were run
   - The phase's logical commits on the milestone branch (subject + body, per CLAUDE.md "Commit Standards")
5. Commit only on the milestone branch. Push to that branch and open (as a draft) or update the
   milestone PR only if I explicitly permit it now. Mark the PR ready for review only after the
   last phase of the milestone. Never push to `main` and never merge (ADR-0011).
