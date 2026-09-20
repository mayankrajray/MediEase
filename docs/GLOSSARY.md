# MediEase — Glossary

| Term | Meaning in this codebase |
|---|---|
| **Clinic** | A tenant. One practice at one address. All tenant data carries its `clinic_id`. |
| **Owner** | Clinic role that manages settings and staff; often also a doctor. |
| **Front desk** | Clinic role that registers patients and runs the queue; includes compounders. |
| **Ops** | MediEase staff using the internal console. Never sees clinical content. |
| **Doctor** | A clinician profile with qualification and registration number; may or may not have a user account. |
| **Schedule** | A doctor's recurring weekly availability. |
| **Schedule exception** | A date-specific change: leave or an extra session. |
| **Session** | One block of consultation time for a doctor on a date (e.g. Mon 10:00–13:00). Materialised from schedules. |
| **Booking mode** | `SLOTS` (fixed times) or `TOKENS` (ordered numbers within a session). |
| **Token** | A queue number within a session in `TOKENS` mode. |
| **Appointment** | A patient's place in a session. Moves through the queue state machine. |
| **Queue** | Today's appointments for a doctor, ordered by slot or token. |
| **Walk-in** | A patient added to today's queue without prior booking. |
| **Visit** | One consultation; holds the clinical record. Locks 24 h after completion. |
| **Addendum** | A dated, attributed note added to a locked visit. |
| **Prescription (Rx)** | The doctor's issued medicines and advice for a visit. Immutable once issued; corrected by a new version. |
| **Rx item** | One medicine line with dose, frequency, timing, duration and patient instructions. |
| **Favourite / Rx template** | Saved medicine line / saved whole prescription for reuse. |
| **Patient link** | Signed, expiring, purpose-bound URL sent to a patient; opened after a last-4-digit phone challenge. |
| **Guardian** | The adult contact of record for a minor patient. |
| **Consent** | The patient's (or guardian's) agreement to receive WhatsApp/SMS messages, recorded by the clinic. |
| **Opt-out** | Patient request to stop messages (e.g. replying STOP). Overrides consent. |
| **Reminder** | A scheduled patient message (follow-up, medicine course, appointment, vaccination). |
| **Template** | A message format approved by the provider (Meta for WhatsApp, DLT for SMS), declared in `templates.yaml`. |
| **Customer service window** | WhatsApp's period after a patient messages the business, during which free-form replies are allowed. |
| **Job** | A row in the `jobs` table representing background work, claimed by the worker. |
| **Dead job** | A job that exhausted its retries and needs a human. |
| **Port** | An interface the application depends on (e.g. `MessagingPort`). |
| **Adapter** | A concrete implementation of a port (e.g. `WhatsAppCloudAdapter`). |
| **Use case** | An application-layer class performing one user action (`BookAppointment`). |
| **Unit of work** | Transaction boundary that also provides tenancy-scoped repositories. |
| **Composition root** | `bootstrap.py` — the one place where settings, adapters and use cases are wired. |
| **request_id** | Correlation ID carried from the browser through API, jobs and provider calls. |
| **ADR** | Architecture Decision Record in `docs/adr/`. |
| **Data Fiduciary / Data Processor** | DPDP Act roles: the clinic decides why and how data is processed; MediEase processes it on the clinic's behalf. |
| **DLT** | India's distributed-ledger registry for commercial SMS senders and templates. |
| **ABDM / ABHA** | Ayushman Bharat Digital Mission / Health Account — national digital health stack (not integrated in MVP). |
