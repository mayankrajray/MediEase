# ADR-0016: Email behind a port, sent over SMTP from the job queue

| Field | Value |
|---|---|
| Status | Proposed (M6a-P4 design, 23 Oct 2026) |
| Date | 2026-10-23 |
| Related | PRD v1.2 FR-AUTH-05, FR-AUTH-08, FR-PUB-03, NFR-07; ADR-0005 (job queue), ADR-0007 (messaging port), ADR-0015; L-04, L-11; M6a-P4 design |

## Context

PRD v1.2 needs email for two things: verifying the email of a patient password account, which
booking requests will require in M6b, and password reset for staff and patients. Later it also
needs email for invitations (P5) and an `EMAIL` notification channel (P7).

MediEase sends no email today. The pilot needs a free tier, and the providers worth considering
offer one only up to a daily cap (Brevo 300 a day, Resend 100 a day). Amazon SES in Mumbai would
keep the data in India, but is no longer free for a new account. All three accept SMTP.

A reset link is a bearer secret. The job queue stores its payloads in plain text.

## Decision

1. **An `EmailPort`, with one SMTP adapter.** The adapter uses the standard library `smtplib`
   (STARTTLS or implicit TLS, with a login). Changing provider is a settings change, with no new
   dependency. A `console` adapter exists for tests and is refused in production.
2. **Brevo's free plan for the pilot**, from a verified domain with SPF, DKIM and DMARC (L-11).
   Brevo processes email addresses outside India, so the privacy notice names it as a processor
   (L-04). If counsel requires processing in India, the same adapter points at SES in Mumbai.
3. **Mailpit on the local stack.** A pinned container catches the mail, and the end-to-end tests
   read it through Mailpit's API.
4. **Sent by the worker, with the secret made at send time.** The request enqueues
   `send_auth_email` with only the purpose and the account. The worker then:
   - creates the token and stores only its SHA-256 digest;
   - retires the account's earlier unused token of that purpose;
   - sends the email.

   No usable secret is ever stored. An SMTP outage delays an email and never fails a sign-up.
5. **Single-use, short-lived tokens** in an `email_tokens` table: verification lasts 24 hours and
   a reset 30 minutes. A token is refused once used or superseded, or if the account's email has
   changed. Verification and reset links open a page that POSTs, so a mail scanner that
   pre-fetches the link consumes nothing.

## Alternatives considered

- **A provider's HTTP API or SDK.** This means code and a dependency per provider.
- **Sending inside the request.** It adds latency, and a provider outage would fail sign-ups and
  resets.
- **Creating the token in the request and putting it in the job.** The reset link would then sit
  in the database as a usable secret.
- **Stateless signed tokens.** A stateless token cannot be made single-use or revoked.

## Consequences

- One more container (Mailpit) runs locally. In production nothing changes beyond SMTP settings.
- Each provider's daily cap limits volume. At pilot scale verifications and resets are a few a
  day; the notification channel (P7) needs the cap watched.
- Real delivery waits for L-11 (the account and the DNS records). Until then everything is tested
  against Mailpit and a fake port.
- Personal data (email addresses) goes to a processor outside India until the provider choice is
  revisited with counsel.
