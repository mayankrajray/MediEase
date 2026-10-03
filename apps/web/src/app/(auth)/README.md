# (auth)

Public pages for people without a session: `sign-in/` and `invite/[token]/` (M1-P6). The layout only
centres the content; `?next=` and `?reason=` are validated in the page before the form sees them.
OTP and password reset arrive later (FR-AUTH-05).
