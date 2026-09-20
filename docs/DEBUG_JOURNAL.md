# MediEase — Debug Journal

A running record of real bugs: what we saw, why it happened, how we fixed it, and what stops it
coming back. Search this file **before** debugging — the same failure may already be solved.

Rules:

- One entry per root cause, newest first.
- No patient data, real phone numbers or clinical content — use IDs and codes.
- Link the fixing commit and the test that now guards it.
- If the lesson is general, also update `DEBUGGING.md` §4 or `RUNBOOK.md`.

## Entry template

```markdown
### YYYY-MM-DD — <short title> (`ERROR_CODE` if any)

- **Milestone / area:** M3 / appointments
- **Symptom:** What was observed, where, by whom. Include request_id(s).
- **Impact:** Who was affected and how badly (local only / staging / pilot clinic).
- **Reproduction:** Minimal steps or the failing test name.
- **Investigation:** Evidence looked at, hypotheses tried and discarded.
- **Root cause:** The actual reason, one or two sentences.
- **Fix:** What changed. Commit: `<sha>` — PR: #<n>
- **Guard:** Test(s) added: `tests/...::test_...`
- **Prevention / follow-up:** Docs updated, alerts added, patterns to avoid.
- **Search keywords:** timezone, midnight, session, IST
```

---

## Entries

_No entries yet. The first one is written when the first real bug is fixed._
