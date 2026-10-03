# (ops)

Internal ops console under `/ops`: clinic onboarding wizard, patient import, clinic health, dead jobs. Never shows clinical content.

M1-P6 ships the frame: `layout.tsx` renders the `SessionProvider` and `OpsShell` (platform staff
only, spec R10; clinic staff are sent to `/queue`). M1-P7 adds `ops/page.tsx` (every clinic with its
onboarding state) and `ops/clinics/new/` (the Create clinic wizard: clinic → doctors → owner
invitation, with the elapsed onboarding time; `?clinic=<id>` resumes a clinic that is still being
set up). The acceptance link is shown once and is not recoverable, by design.
