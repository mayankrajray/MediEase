# (ops)

Internal ops console under `/ops`: clinic onboarding wizard, patient import, clinic health, dead jobs. Never shows clinical content.

M1-P6 ships only the frame: `layout.tsx` renders the `SessionProvider` and `OpsShell` (platform staff
only, spec R10; clinic staff are sent to `/queue`), and `ops/page.tsx` is a placeholder. The Create
clinic wizard (spec §6) is planned separately; the API behind it is complete (M1-P5, RUNBOOK §10).
