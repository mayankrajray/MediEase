# ADR-0017: Domain events and a notification service, dispatched in the publishing transaction

| Field | Value |
|---|---|
| Status | Accepted (M6a-P7, approved and built 23 Oct 2026) |
| Date | 2026-10-23 |
| Related | PRD v1.2 C11, FR-NTF-02..06, FR-MSG-04, FR-REM-04, NFR-13; ADR-0005 (job queue), ADR-0007 (messaging port), ADR-0016 (email port); M6a-P7 design |

## Context

PRD v1.2 asks for features to publish domain events. A notification service then maps each event
to recipients and channels: in-app now, WhatsApp through the messaging port, and email and SMS
later. Each recipient has channel preferences, a notification centre per role, at-least-once and
idempotent delivery, and nothing clinical in the text.

Today there is no event concept. Two features enqueue a WhatsApp job themselves:

- a booking or reschedule enqueues `send_booking_confirmation`;
- issuing a prescription enqueues `send_rx_link`.

Their handlers re-check consent and facts at send time and are idempotent by key (M5-P2). Staff
get no notifications at all. Patient accounts are not linked to clinic patients until M6b, so a
patient can only be reached by WhatsApp or SMS for now.

The job table is already a transactional outbox: a job commits or rolls back with the change that
enqueued it, and a dedupe key makes it idempotent.

## Decision

1. **Events are published in the change's own transaction and dispatched there, in process.** A
   use case calls `publish(uow, event)`. The event is a small frozen dataclass of IDs and enums.
   `NotificationService.dispatch` then, in the same transaction:
   - resolves the recipients, either staff users by role or doctor, or the patient;
   - reads their channel preferences;
   - writes one row per in-app notification, unique per recipient and event key;
   - asks each external channel for its delivery. For WhatsApp that means enqueuing the existing
     send job, with its key unchanged.

   An event therefore exists exactly when the change commits. External deliveries keep the
   queue's at-least-once retry and the sender's at-most-once message per key.
2. **Channels behind one interface.** `IN_APP` writes `notifications` rows. `WHATSAPP` adapts the
   M5 jobs and is the only path from a feature to the messaging port. `EMAIL` and `SMS` are
   declared but deliver nothing until they are built.
3. **Text from a typed catalogue.** Each notification kind has an English title built only from
   typed values: a first name with a patient code, a doctor's name, a time, a role or a count.
   There is no free text and no clinical kind. The title is rendered when the notification is
   created and stored with its deep link.

## Alternatives considered

- **Dispatching from a worker job per event.** Fan-out happens off the request. But each event
  then waits for the queue's poll, and there are twice as many jobs. A clinic has a handful of
  staff, so fan-out in the transaction is cheap.
- **An `events` table polled by a dispatcher.** This is a second queue next to the job table, with
  its own retries, reaper and retention.
- **A message broker (Redis, RabbitMQ).** This is new infrastructure that ADR-0005 decided against
  at this scale.
- **Features keeping their direct WhatsApp calls.** This contradicts FR-NTF-02 and keeps the
  recipient rules spread across features.

## Consequences

- A slow recipient lookup would slow the publishing request. Every lookup is one indexed query on
  a small table, and the dispatcher is tested for its query count.
- Events published by the worker (a message that failed) use the same `publish` in the worker's
  transaction.
- Reminders keep their own scheduler and its quiet hours (FR-REM-04): a reminder is due at a
  time, not raised by a change. P8 reviews whether due-time notifications join the service. The
  STOP reply's confirmation is a protocol answer, not a notification, and stays as it is.
- The notification text is English at MVP (NFR-11).

## As built (M6a-P7)

- **Channels are two code paths in `NotificationService`, not an interface.** `IN_APP` writes
  `notifications` rows; `WHATSAPP` calls the M5 `enqueue_booking_confirmation` and
  `enqueue_rx_link`. `EMAIL` and `SMS` exist only as preference channels. A `Channel` protocol
  is worth adding when a third channel delivers something; until then it would have one caller.
- **One dispatch costs one query per lookup**, whatever the number of recipients (a test counts
  four statements for a failed message: patient, members, their choices, one insert).
- **A failed message is published from both places a message fails**: the sender's final failure
  and the webhook's `FAILED` transition. `ProcessWebhookEvent` now requires the ID port.
