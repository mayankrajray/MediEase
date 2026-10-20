# ADR-0014: Each clinic's own WhatsApp number, and one consolidated MediEase invoice

| Field | Value |
|---|---|
| Status | Proposed (designed in M6; built in M8) |
| Date | 2026-10-20 |
| Deciders | Developer (product owner), engineering agent |
| Related | PRD v1.1 C5, FR-BIL-WA-01..02; ADR-0003 (tenancy), ADR-0005 (jobs), ADR-0007 (messaging port); `docs/milestones/M8-multi-clinic-whatsapp.md` |

## Context

Today MediEase sends every clinic's messages from one platform number configured in the
environment (M5). The developer wants each clinic to send from its own number, connected through
Meta's Embedded Signup (an existing WhatsApp Business account, a new one, or an existing WhatsApp
Business app number kept in use), and one MediEase invoice per clinic: the subscription, plus the
clinic's actual WhatsApp usage, plus a markup on that usage. The developer does not want MediEase
to become a Meta Tech Provider or Solution Partner.

Meta's rules shape the options:
- Onboarding other businesses through Embedded Signup is done by a Meta Tech Provider or Solution
  Partner app.
- A business onboarded by a Tech Provider pays Meta itself with its own payment method. Only a
  Solution Partner can share a credit line with the business's account and be billed for it (the
  "Bill To Party"). So a consolidated invoice of actual usage needs someone's credit line.
- Some Solution Partners (BSPs) run partner programmes in which a software company resells under
  the BSP's credit line and receives one bill for all its clients' accounts; for example
  360dialog's "Partner-Paid" model, where the partner assumes the costs of every account in its
  hub.

## Decision

- **Partner through a BSP's partner programme** with a partner-paid (wholesale) model. MediEase
  becomes the BSP's partner, not a Meta Tech Provider or Solution Partner itself. Clinics onboard
  through the BSP's Embedded Signup or integrated onboarding under MediEase's brand, the BSP's
  credit line pays Meta, MediEase pays the BSP one bill and invoices each clinic. The BSP is chosen
  at M8's start (price, India support, API closeness to Meta's Cloud API).
- **A per-clinic connection behind the existing port.** A `whatsapp_connections` table per clinic
  (provider, account ID, phone number ID, display number, encrypted credentials, status, quality,
  messaging limit). The sender looks up the connection for the job's clinic. The M5 platform
  number stays as a fallback connection for local, test and demo use. Adapters: Meta Cloud API
  (M5, kept) and the chosen BSP's API.
- **Per-clinic templates and webhooks.** Templates are provisioned and tracked per connection;
  a clinic cannot send a template until it is approved for its own account. Webhook events are
  routed to their clinic by account and phone number ID; a STOP to a clinic's number opts the
  patient out at that clinic only (replacing M5-P5 decision 2A once numbers are per clinic).
- **An append-only usage ledger, separate from `messages`.** One row per billable event: clinic,
  connection, message, category, event time, billing period, provider cost, markup and price
  version. Invoices are built from the ledger and checked monthly against the BSP's or Meta's
  usage report for each account.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Become a Meta Solution Partner | Full control, Meta's own credit line | Meta's programme requirements, liability for all clinics' spend, long approval | The developer rejected the burden |
| Become a Meta Tech Provider | Direct Embedded Signup | Each clinic pays Meta itself: two bills, no consolidated invoice of usage | Contradicts the single-invoice decision |
| Keep one platform number for all clinics | Works today; one bill | Messages show MediEase, not the clinic; one quality rating and limit for everyone; templates shared | Not production-ready for multiple clinics |

## Consequences

- Positive: one invoice per clinic; tenancy holds from connection to ledger to invoice; the M5
  code keeps working through the fallback connection; no Meta partner programme for MediEase.
- Negative / costs: dependency on one BSP (pricing, uptime, its API's differences); MediEase is
  liable to the BSP for every clinic's usage, so unpaid invoices are MediEase's loss; MediEase
  itself still needs a verified business and a website for the BSP partnership.
- Follow-ups and triggers to revisit: choose the BSP and confirm its partner-paid terms in India;
  credit limits per clinic; move to a direct Meta partnership if volume justifies it.
