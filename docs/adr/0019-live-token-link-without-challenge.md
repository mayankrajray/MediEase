# ADR-0019: The live token link needs no last-4 check

| | |
|---|---|
| Status | Accepted (approved by the developer 26 Oct 2026; the R71 protections and the ownership check on issue are mandatory) |
| Deciders | Developer |
| Related | FR-QUE-06, FR-MSG-04, NFR-07, ADR-0006 (tokens), M4-P5 prescription link |

## Context

FR-QUE-06 asks for a "you are 3rd in line" link a patient opens on their phone. The prescription
link (M4-P5) asks for the last 4 digits of the phone before it shows anything, because it shows
clinical content. The live link would show far less: the clinic and doctor (both public on the
clinic page), the patient's own token number or slot time, how many are ahead and which token is
being seen. A patient checks it repeatedly while waiting, often on a shared or borrowed phone.

## Decision

The live link is a signed token (the existing `header.claims.mac` format, a new purpose
`QUEUE_VIEW`) naming one appointment, valid from the start of the session's day until 2 hours
after it ends. Opening it needs **no challenge**. The page shows only the fields above; never the
patient's name, phone, reason, age or anything from the visit. It is `noindex`, never cached,
rate limited per link and per caller like the prescription link, and refuses a cancelled
appointment's link with a plain message.

*As built (M6b-P6):* the token is a new token **kind** (`Kind.QUEUE`, claims clinic, appointment,
not-before and expiry) rather than a `patient_links` purpose: it is stateless, so no row and no
CHECK change, and it cannot be revoked before it expires (accepted for this content). Limits are
120 reads a minute per caller and 30 per link.

## Consequences

- Anyone holding the link learns that *someone* has token 7 with Dr X at that clinic today and
  where they are in the queue. That is the same information a person in the waiting room sees.
- The link cannot be used to find a patient: tokens are unguessable (256-bit signature) and the
  page names nobody.
- Reissuing a link does not revoke the earlier one (they expire the same evening); a clinic that
  needs a link stopped cancels or reschedules the appointment, which voids it.

## Alternatives considered

- **The last-4 check first.** Protects nothing clinical, adds a step every time the patient looks,
  and fails on shared family phones where the number is someone else's.
- **Signed-in portal only.** Excludes walk-ins and anyone without an account, who are most
  patients in the pilot.
