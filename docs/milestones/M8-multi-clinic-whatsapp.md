# M8 — Multi-clinic WhatsApp and consolidated billing: design notes

| Field | Value |
|---|---|
| Status | Designed 20 Oct 2026 (developer's decisions below); built after M6 and M7. Each phase is designed in detail and approved at its start |
| ADR | ADR-0014 (Proposed) |
| Covers | FR-BIL-WA-01..02; PRD v1.1 C5 |
| Exit criterion | Two clinics, each on its own number, send and receive independently; one month's usage of each appears on that clinic's MediEase invoice only, and matches the provider's report |
| Outside dependencies | A BSP partner account with a partner-paid model (L-08, new); MediEase's own business verification and website for that partnership; for testing before then, Meta's development mode with test accounts |

## Decisions already taken (20 Oct 2026)

1. **One consolidated invoice:** subscription + actual WhatsApp usage + MediEase's markup on usage.
2. **No Meta partner programme for MediEase:** partner with a BSP's partner-paid model instead
   (ADR-0014).
3. **STOP is per clinic:** a STOP to a clinic's number opts the patient out at that clinic only.

## What exists (M5) and what changes

| Area | M5 | M8 |
|---|---|---|
| Sender | One `MessagingPort` built at start-up from `WHATSAPP_*` settings | A connection per clinic, looked up by the sender for each job; the M5 settings become the platform's fallback connection |
| Onboarding | None | Owner-only Embedded Signup (or the BSP's onboarding) from clinic settings |
| Templates | `templates.yaml`, one approval | Provisioned per connection from `templates.yaml`; sends blocked until approved for that account |
| Webhooks | One endpoint; parser drops account and phone number IDs; STOP across clinics | Same endpoint (or the BSP's); events routed by account and phone number ID; per-clinic STOP; account, template, quality and disconnection events |
| Credentials | `WHATSAPP_ACCESS_TOKEN` | Platform: app or partner keys. Per clinic: encrypted token (Fernet, the `MESSAGING_PHONE_KEYS` pattern), rotation, revocation marks only that connection disconnected |
| Cost | `messages.cost_millipaise`, ops monthly report | Append-only `messaging_usage` ledger, billing periods, invoices, reconciliation |

## Data (planned)

| Table | Key columns | Notes |
|---|---|---|
| `whatsapp_connections` | clinic_id, provider, waba_id, phone_number_id (unique), display_phone, token_encrypted, status (`PENDING`, `CONNECTED`, `ACTIVE`, `DISCONNECTED`, `ERROR`), quality_rating, messaging_limit, connected_by, connected_at | Tenant-scoped; one active connection per clinic |
| `whatsapp_templates` | clinic_id, connection_id, key, version, language, provider_template_id, status, rejected_reason | Tenant-scoped; filled by a provisioning job |
| `messages` | + `connection_id` (nullable: the fallback) | Existing |
| `messaging_usage` | clinic_id, connection_id, message_id, category, billable, event_at, billing_period (YYYY-MM, clinic zone), provider_cost_millipaise, markup_millipaise, price_version | Append-only (triggers like `audit_events`); one row per billable event, unique per message |
| `billing_periods`, `invoices`, `invoice_lines` | clinic_id, period, status (`OPEN`, `CLOSED`, `ISSUED`, `PAID`), lines: subscription, WhatsApp usage, markup | Tenant-scoped; an invoice reads only its clinic's ledger |
| `subscription_plans`, `clinic_subscriptions` | plan, price, markup rate, valid from | Platform plan data plus each clinic's plan |

## Flows

1. **Connect:** the owner opens *Connect WhatsApp* → the BSP or Meta signup popup → the server
   receives the account and phone number IDs and an authorisation code → it exchanges the code
   for the clinic's token, subscribes the app to the account's webhooks, registers the number,
   stores the encrypted connection, audits `whatsapp.connected`, and enqueues template
   provisioning.
2. **Send:** `MessageSender` resolves the job's clinic connection (or the fallback), checks the
   template is approved for it, and sends as today; the message row records the connection.
3. **Receive:** the webhook is verified as today, stored once, and routed by account and phone
   number ID to the clinic; statuses update messages as today; a STOP opts out at that clinic;
   account events update the connection.
4. **Meter:** a delivered, billable status writes one `messaging_usage` row at that day's price
   and markup.
5. **Bill:** at month end, in each clinic's zone, a job closes the period, builds the invoice from
   the subscription and that clinic's ledger only, and compares the totals with the provider's
   report for that account; a mismatch beyond a tolerance is flagged for ops.

## Phases (planned)

| Phase | Builds | Needs the provider |
|---|---|---|
| P1 | Connections table, encrypted credentials, per-clinic sender lookup with the fallback | No |
| P2 | Onboarding flow (API and owner screen) | Development mode |
| P3 | Per-connection template provisioning and status; account webhooks | Development mode |
| P4 | Webhook routing by account and phone number ID; per-clinic STOP | Development mode |
| P5 | Usage ledger, plans and subscriptions, billing periods, invoices, reconciliation | No |
| P6 | Owner billing page, ops billing console, invoice PDF | No |

## Open for M8's start

- Choose the BSP; confirm its partner-paid terms, prices in India, and how close its API is to
  Meta's Cloud API.
- Markup basis: a percentage of usage, or a fixed amount per message.
- Payment collection: invoices first (manual UPI, as PRD §12); automated collection later.
