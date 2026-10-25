# ADR-0018: The soft hold is the pending booking request, counted under the session lock

| Field | Value |
|---|---|
| Status | Accepted (approved 25 Oct 2026; built in M6b-P4, 26 Oct 2026) |
| Date | 2026-10-25 |
| Related | PRD FR-BKG-02, FR-APT-04, FR-DIS-05; spec `booking-requests.md` R10, R17–R19; appointments D10 (closing booked sessions); ADR-0005 (job queue) |

## Context

A patient's booking request must hold its slot (or a place in a token session) for a
clinic-set time, default two hours, so that two patients are never both told "requested" for the
same slot and staff do not book it by phone meanwhile (FR-BKG-02, FR-APT-04).

Today a session's free places are `capacity − booked_count`, changed only under the session's
`FOR UPDATE` lock, and a slot is taken when an active appointment has its `slot_start`. Schedule
changes (`reconcile`) retire a session with no bookings and close one with bookings. There is no
hold anywhere.

## Decision

1. **The hold is the request.** A `booking_requests` row in `PENDING` with
   `hold_expires_at > now` is a live hold. No other table and no counter.
2. **Counted under the same lock.** Every write that takes a place — a staff booking, a request,
   and P5's accept — locks the session as booking does (`lock_sessions`), then counts live holds
   for that session: free places = `capacity − booked_count − live holds`; a slot is unavailable
   when it is booked or under a live hold. There is no unique index on the slot: a lapsed
   `PENDING` request must not stop the next request, so the session lock is the guard.
3. **Time ends a hold.** Nothing runs when a hold lapses; every reader applies the `now`
   predicate. The request itself stays `PENDING` until P5's expiry changes its status.
4. **Staff respect holds, and may override them explicitly.** A staff booking into a held slot is
   refused with `APT_SLOT_HELD` and the hold's end. Staff may book anyway with `override_hold`
   (a confirmed UI action): the blocking hold ends in the same transaction and
   `appointment.hold_overridden` is audited, so a patient can never block the clinic. A hold is
   also capped at the request's response deadline.
5. **Schedule changes keep sessions with pending requests.** `reconcile` treats a session with
   any `PENDING` request (live hold or not) as booked: it is closed, never deleted or retired,
   because the request points at the row. It is not counted among the bookings to move.
6. **Accept converts in one transaction (P5).** Under the lock, the request becomes `ACCEPTED`
   and the appointment is booked with `booked_count` + 1; the hold disappears because the
   request is no longer `PENDING`.

## Consequences

- No job is needed for correctness; P5's expiry job only tells people and closes the request.
- Reads must always pass `now`; a forgotten predicate would hold a slot forever. The predicate
  lives in one repository method used by every place-taking path, with tests in slot and token
  modes.
- One extra indexed query per locked booking. At pilot scale (≤ 50 clinics) this is negligible.
- `booked_count` keeps meaning "appointments", so reports and the queue are unchanged.

## Alternatives considered

- **A `held_count` on `sessions`.** It needs a job to decrement it on time, drifts if a job is
  late or lost, and changes what reconcile and reports read.
- **No hold, first accept wins.** Two patients could both be told "requested", against FR-BKG-02.
- **Book a tentative appointment.** A status that every staff screen, reminder and count would
  have to exclude; the queue and reminders would need guarding everywhere.
