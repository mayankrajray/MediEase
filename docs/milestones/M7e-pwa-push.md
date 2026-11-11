# M7e — Installable app (PWA) and web push notifications

**Status:** planned; starts after M7d. Issue #73, branch `m7e/73-pwa-push` (from
`m7d/71-discovery-booking`; its PR targets that branch until M7d is merged), one PR.

**Why:** WhatsApp sending is blocked by a Meta Business setting (`OAuthException code 10`, M7c-P6),
and patients of small clinics should not depend on WhatsApp for reminders. The mentor's direction
(11 Nov 2026): make MediEase an installable app that sends its own notifications. The developer's
brief ("P7 Frontend Work, Brand Integration & Progressive Web App") is the source; this file is the
plan agreed from it.

## 1. Decisions (developer, 11 Nov 2026)

1. The logo stays at **`/brand/`** (`apps/web/public/brand/`; emails and documents already link
   there). The brief's `public/branding/` is not used; Next.js serves only `apps/web/public/`.
2. Push for **patients and clinic staff**.
3. Lock-screen text is **generic only** ("You have an upcoming appointment. Open MediEase to view
   details."); no clinic name, doctor, time or anything clinical in a push payload.
4. **Appointment and follow-up reminders for app users** (accounts linked to the record), not only
   for WhatsApp-consenting patients.
5. **`pywebpush`** (MPL-2.0) for the encryption and VAPID signing.
6. Order: **M7d first, then M7e**. Real-phone tests during development through a **temporary
   tunnel**; the developer will give a production HTTPS URL later.

## 2. What exists (audit, 11 Nov 2026)

- **The brief's "P7"** is M7c-P7 (design system and modules M1–M10), done; the logo files are in
  `apps/web/public/brand/` and every on-screen logo comes from the `Logo` component.
- **No PWA:** no manifest, no service worker, no PWA library (`apps/web/package.json`).
- **Notifications:** patient notices (`patient_notifications`, one per `(account_id, event_key)`,
  titles rendered on read) and staff notices (`notifications`, one per
  `(clinic_id, recipient_user_id, event_key)`), preferences per kind and channel, the bells, and
  booking-answer email by job. One dispatcher: `NotificationService` and `notify_patient`, in the
  change's transaction. Staff channels already declare `WHATSAPP`, `EMAIL`, `SMS` with nothing
  delivering them.
- **Reminders:** appointment and follow-up reminder rows exist only when
  `patient.may_receive_whatsapp`; sent by `SendReminder` over WhatsApp. Medicine-due notices are
  in-app only (`notify_due`, a 5-minute sweep on the P3 engine).
- **Worker:** PostgreSQL job table, dedupe keys, `SKIP LOCKED`, backoff 1/5/15/60 min; a system
  job kind needs a migration of `ck_jobs_system_kind`.
- **Web shell:** a nonce CSP (`default-src 'self'` covers a same-origin `/sw.js` and manifest);
  `proxy.ts` redirects unknown signed-out paths to sign-in, so `/sw.js`, the manifest and the
  offline page must be listed as public.
- **API dependencies:** `cryptography` is present; `pywebpush` is not.

## 3. Plan

| Phase | Work | Tests |
|---|---|---|
| E1 Installable app | `app/manifest.ts` (name and short name MediEase, description, brand theme and background colours, `standalone`, start URL `/portal` for patients); icons 192, 512 and maskable from the emblem; a hand-written `public/sw.js` (cache-first for `/_next/static/`, `/brand/` and icons; network-only for everything else; an offline page for failed navigations; versioned cache and `skipWaiting` on the user's "Update" choice); registration in a small client component; the proxy allow-list; an install button shown once (dismissal remembered), installed-state detection, iOS guidance | Unit (manifest, the cache rules: API and portal paths never cached); journey: manifest valid, service worker active, offline page shown, API not served from cache; page weight |
| E2 Subscriptions | Migration `0043`: `push_subscriptions` (owner: a patient account **or** a staff user, never a clinic; endpoint and keys encrypted with the existing key-rotation cipher; user agent label; created, last success, disabled); a `PUSH` channel in both preference sets; endpoints `POST`/`DELETE` and `GET` for the current device, for the portal and for staff; OpenAPI and generated types | Ownership and isolation (another account or user cannot see or use one), CSRF, re-subscribe idempotent, delete, limits |
| E3 Delivery | One `send_push` job per notice and device set (dedupe on the notice's event key), from `notify_patient` and the staff in-app dispatch; a `WebPushPort` with the `pywebpush` adapter and a console adapter for local and CI; generic text per kind (EN and HI); 404/410 from the push service disables the subscription; 429 and 5xx retried on the job backoff; quiet hours for kinds that respect them; structured logs with no payload | Payload has no PHI; multiple devices; expired subscription removed; retry; one push per event even on replays |
| E4 Reminders for app users | Reminder rows also for patients with a linked account (same timing rules, quiet hours, cancel and move with the appointment); new patient notice kinds for an appointment reminder and a follow-up reminder (in-app and push; WhatsApp stays where consented) | Time zones, cancel, reschedule, one reminder per kind and revision, WhatsApp unchanged |
| E5 Settings, offline, docs | Account (portal) and Settings → Notifications (staff): this device on/off, blocked-by-browser explanation, per-kind switches; the click opens the notice's link (sign-in first if the session ended); ADR, spec, DATA_MODEL, ERRORS, RUNBOOK (VAPID keys, `make vapid-keys`, tunnel test), `.env.example` | Full suites, `make smoke`, full `make e2e`; real devices: Android Chrome (browser and installed), iOS 16.4+ installed |

Estimate: about 4 working days.

## 4. Configuration

`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (secret, server only), `VAPID_SUBJECT` (`mailto:` of the
operator), `PUSH_PROVIDER` (`console` locally and in CI, `webpush` when keys are set; console refused
in production). Generated by `make vapid-keys`; never committed. Service workers and push need HTTPS
(localhost is exempt): real phones are tested through a temporary tunnel.

## 5. Limits to state plainly

- iPhone and iPad receive push only from an app added to the Home Screen (iOS 16.4+).
- Push delivery is best effort; the notice in the database stays the record, and the bell shows
  it whether or not a push arrived.
- Offline, the app shows an offline page; it never queues or pretends a clinical change succeeded.
- Patient pages are at 185–194 KB of 200 KB: the registration script must stay small (measured).

## 6. Not in M7e

Native apps; SMS as a paid fallback; offline clinical data; a push provider service (browsers'
own push services are used, at no cost).
