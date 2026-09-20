# ADR-0007: WhatsApp-first messaging behind a provider-agnostic port

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | FR-MSG, FR-REM, PRD §6.4 principle 1 |

## Context

Patients and clinics already live in WhatsApp; SMS is the fallback for patients without WhatsApp.
The WhatsApp Business Platform prices messages per message (since 1 July 2025), requires approved
templates for business-initiated messages, and makes utility templates free inside an open
customer-service window. Providers, prices and policies change.

## Decision

- A `MessagingPort` with `send_template()`; adapters: console (dev/test), WhatsApp Cloud API
  (direct with Meta), SMS (Indian DLT-registered provider).
- Templates declared as data in `templates.yaml` (provider name, language, category, variables,
  version). Utility category only in the MVP.
- Message variables are non-clinical: clinic name, date/time, signed link.
- One MediEase sender number for the pilot; the clinic name appears in every template.
- Inbound STOP keywords opt the patient out.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| A WhatsApp BSP (e.g. Gupshup, Interakt, AiSensy) | Faster onboarding, dashboards | Markup on Meta pricing, another processor holding patient contact data | Keep as an adapter option if Meta onboarding stalls |
| SMS only | Universal reach | Poor engagement, DLT overhead, no read receipts | Patients live in WhatsApp |
| Clinic-owned numbers from day one | Brand trust | Per-clinic Meta onboarding kills the < 60-min goal | Deferred to P2 |

## Consequences

- Template approval is on the critical path for M5 (TASKS L-01, L-02).
- Messaging cost is ours under flat pricing; tracked per clinic (FR-MSG-07).
- Switching to a BSP means writing one adapter, not changing use cases.
