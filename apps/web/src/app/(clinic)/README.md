# (clinic)

Authenticated clinic dashboard routes. The layout renders the client `SessionProvider`, which
asks the API who is signed in (the session tokens are HttpOnly and `me_access` is not sent on page
requests) and sends anyone else to `/sign-in`.

- `select-clinic/` — the chooser for people in several clinics (M1-P6).
- `(workspace)/` — pages that need a working clinic, framed in the dashboard shell; its layout is
  `WorkspaceGuard`. Today: `queue/` (landing: the live queue board, M3-P5), `settings/schedule/` (owners, M3-P5). Later: `patients/`, `visits/[id]/`,
  `follow-ups/`, `settings/`.
