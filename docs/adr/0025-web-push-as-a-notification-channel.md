# ADR-0025: Web push as a notification channel, with devices owned by a person

| Field | Value |
|---|---|
| Status | Accepted (M7e-E2, 12 Nov 2026) |
| Date | 2026-11-12 |
| Deciders | Developer (design `docs/milestones/M7e-pwa-push.md`, approved 12 Nov 2026); agent |
| Related | FR-NTF-01..06, NFR-08, NFR-19; ADR-0017 (notification service), ADR-0015 (patient accounts), ADR-0003 (tenancy); spec `docs/specs/web-push.md` |

## Context

WhatsApp sending is blocked by a Meta Business setting, and patients of small clinics should not
depend on WhatsApp for reminders. MediEase became an installable app in M7e-E1. Browsers can
deliver notifications through their makers' push services (FCM, Mozilla, Apple, Windows) when the
server sends a message encrypted for the browser and signed with a VAPID key, at no cost.

Three questions needed answers before any delivery code: who owns a device, how its secrets are
kept, and how the server is kept from being pointed at arbitrary addresses, since it will POST to
whatever endpoint a browser hands over.

## Decision

Web push is a channel of the existing notification service (ADR-0017), beside in-app and email,
with these rules:

1. **Ownership.** A device (`push_subscriptions`) belongs to exactly one patient account or one
   staff user, never a clinic (a CHECK). A staff member's device works in every clinic they belong
   to. Deleting the account or user deletes its devices.
2. **One row per browser.** The endpoint's SHA-256 digest is unique. The same browser subscribing
   again refreshes its keys. Another person subscribing the same browser takes the device over: a
   shared phone delivers to whoever turned notifications on last.
3. **Secrets at rest.** The endpoint and both keys are stored encrypted with the same Fernet keys
   and rotation as phone numbers (`MESSAGING_PHONE_KEYS`). They are never returned by the API,
   logged or audited. A device is shown by a label from a fixed vocabulary ("Chrome on Android"),
   never the user agent.
4. **Endpoints are allow-listed.** Only https URLs at the browsers' push services are accepted
   (`fcm.googleapis.com`, `updates.push.services.mozilla.com`, `web.push.apple.com` and
   `*.push.apple.com`, `*.notify.windows.com`), on port 443 and without credentials. Anything
   else is 422, so the server never posts to an internal or arbitrary address (request forgery).
5. **Limits.** At most 10 active devices per person (409 `PSH_TOO_MANY_DEVICES`) and 30 subscribe
   calls an hour (429 `PSH_RATE_LIMITED`).
6. **Preferences.** `PUSH` is a channel in both preference sets, on for every kind unless turned
   off. Staff may choose `IN_APP` and `PUSH` only.
7. **Content (E3).** A push payload carries generic text per kind and the notice's link, never a
   name, clinic, doctor, time or anything clinical (design §1 decision 3). The notice in the
   database stays the record; push is best effort.
8. **Audit.** Adding and removing a device are audited (`push_device.added`, `.removed`) with the
   device's ID and label only. They belong to no clinic, so they never reach an owner's log.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Devices owned by a clinic membership | Mirrors staff notices, which are per clinic | A person in two clinics would need two subscriptions for one browser; patients have no membership | A device is a person's, not a clinic's |
| Accept any https endpoint | Works with any future push service | The server would POST to any URL a browser (or an attacker) sends: internal services, cloud metadata | Request forgery; the four services cover every browser we support |
| Store the endpoint in plain text with a unique index | Simple lookups | The endpoint is a capability: anyone with it and the keys can send to the device | Encrypted at rest, found by digest |
| A third-party push provider (OneSignal, Firebase SDK) | Dashboards, retries | Cost, a processor holding patient device data, a heavier client | The browsers' own services are free and enough |

## Consequences

- Positive: one more channel without a new provider; a shared device cannot leak another person's
  notices once it changes hands; nothing about a device is readable at rest.
- Negative / costs: Fernet keys now protect device secrets too, so key rotation must keep old keys
  until every device has resubscribed or been removed. A browser not on the allow-list (a new push
  service) needs a code change.
- Follow-ups and triggers to revisit: E3 adds delivery (VAPID private key, `pywebpush`, expired
  endpoints disabled on 404/410). Revisit the allow-list if a supported browser moves its push
  service. Revisit ownership if devices ever need per-clinic quiet hours.
