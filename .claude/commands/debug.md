---
description: Investigate a bug using the MediEase debugging protocol
argument-hint: <symptom, request_id, error code>
---

Investigate: **$ARGUMENTS**

Follow CLAUDE.md "Debugging Protocol" and `docs/DEBUGGING.md`:

1. Search `docs/DEBUG_JOURNAL.md` and `docs/ERRORS.md` for this symptom or code; quote any match.
2. Use the symptom table in `docs/DEBUGGING.md` §4 to name the likely layer.
3. Gather evidence: logs filtered by request_id (`docker compose logs … | jq`), related job/message
   rows (non-clinical columns only). Show what you looked at.
4. State one hypothesis at a time and the observation that would disprove it.
5. Propose the root-cause fix and the test that fails without it. Do not change code until I approve.
6. After the fix is approved and verified, draft the `docs/DEBUG_JOURNAL.md` entry.

Never widen permissions, remove tenancy scoping, swallow exceptions, or skip tests to make a symptom disappear.
