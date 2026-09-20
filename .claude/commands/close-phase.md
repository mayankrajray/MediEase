---
description: Prepare the hand-off for a phase the developer has tested
argument-hint: <phase id>
---

Close phase **$ARGUMENTS** (only after I confirm I tested it):

1. Update `TASKS.md`: mark the phase ✅, set the next phase `▶ ACTIVE`, update "Current focus".
2. Add the change to `CHANGELOG.md` under Unreleased.
3. Output:
   - Summary with requirement IDs
   - Changed Files manifest (added / modified / deleted)
   - Verification steps that were run
   - Suggested Conventional Commit message
Do not run git commands.
