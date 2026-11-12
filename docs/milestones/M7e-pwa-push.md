# M7e — Installable app (PWA) and web push notifications

**Status:** active from 12 Nov 2026; design and the §7 points approved by the developer on
12 Nov 2026. Issue #73, branch `m7e/73-pwa-push` (rebased onto `main` after M7d merged in PR #72),
PR #74, one PR.

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

## 7. Open points, approved as recommended (developer, 12 Nov 2026)

The developer approved Q1–Q4 as recommended (A, A, A, A) on 12 Nov 2026.

The audit in §2 still holds (next migration `0043`, next ADR 0025, no manifest or service worker,
no `pywebpush`, reminders gated on `may_receive_whatsapp`). The four points:

| # | Question | Options | Recommended |
|---|---|---|---|
| Q1 | Start URL of the one manifest (staff and patients share the origin) | A: `/`, which already sends a signed-in visitor to Today or the portal. B: `/portal`, so staff open the app on the patient sign-in | **A** |
| Q2 | Page weight: `/` is at 204.4 KB of 204.8 KB and `/portal/request` at 195.8 KB | A: register the service worker from a tiny script loaded after the page, outside the first-load bundle, measured on every patient page. B: register only on portal and staff pages, never on `/` | **A**, falling back to B for `/` if the measurement says so |
| Q3 | Who may get app reminders (E4) when the patient has not consented to WhatsApp | A: the linked account holder only, by turning push on for this device (the browser's permission plus the per-kind switch is the consent); WhatsApp still needs clinic-recorded consent. B: only patients who also consented to WhatsApp | **A** (decision 4) |
| Q4 | How push is tested | A: journeys check the manifest, service worker, offline page and subscription calls with the browser's push manager stubbed and the console adapter; real delivery on the developer's Android and iPhone through a tunnel (`cloudflared` quick tunnel run by the developer). B: also a Playwright test against a real push service | **A**: a container cannot reach the browsers' push services reliably |

Also proposed: ADR-0025 "Web push as a notification channel" (VAPID, payload rules, subscription
ownership, failure handling), written at E2.

## 8. As built

### E1 — Installable app (12 Nov 2026)

| Part | Where | Notes |
|---|---|---|
| Manifest | `src/lib/pwa/manifest.ts`, served by `src/app/manifest.webmanifest/route.ts` | Start URL and scope `/`, `standalone`, brand theme `#147d72`, canvas background. A route, not `app/manifest.ts`, so it is linked only where the layouts ask (below) |
| Icons | `public/icons/icon-192.png`, `icon-512.png`, `maskable-512.png` | Rendered once from `src/app/icon.svg` on white. The maskable one keeps the emblem in the 80% safe zone |
| Service worker | `public/sw.js` | Cache-first for `/_next/static/`, `/brand/`, `/icons/`. Navigations go to the network, with `/offline.html` when it fails. The API and other origins are left alone. It never stores a page or an API answer. Old `mediease-*` caches are removed on activate. A new version waits for `SKIP_WAITING` |
| Offline page | `public/offline.html` | Plain HTML, English and Hindi, no script; "Nothing was sent or changed", 112 for emergencies |
| Registration | `public/sw-register.js` (1.5 KB) via `features/pwa/RegisterServiceWorker.tsx` | An async `<script>` with the response's CSP nonce, scope `/`. It passes install and update moments to the page as `mediease:*` events |
| Prompts | `features/pwa/AppPrompts.tsx`, `AppPromptsGate.tsx`, `signals.ts`, `lib/i18n/pwa.ts` | Install once per device (remembered in `localStorage` `me_app_prompt`), iPhone Add to Home Screen steps, and "A new version is ready · Update". The gate loads the prompts only when there is something to offer. Shown on staff Today and on the portal's Home and Account |
| Public paths | `src/proxy.ts` | `/manifest.webmanifest`, `/sw.js`, `/sw-register.js`, `/offline.html`, `/icons/` |
| Image | `apps/web/Dockerfile` | `public/` is now copied into the runtime image. It was missing, so `/brand/` (the logo emails link to) answered 404 in the container |

**Q2 in practice (fallback B).** The manifest link, the iPhone tags and the registration script
are added by the staff, ops, staff sign-in and portal layouts only. They are left out of the
landing page, `/find`, clinic and doctor pages and the token pages (`/p`, `/q`, `/r`). `/` was
at 204.7 of 204.8 KB, and next/script plus the prompts in the shells added 6 KB to every portal
page. One registration covers the whole site (scope `/`), so a page that does not register the
worker is still controlled by it and gets the offline page.

**First-load weights after E1 (360 px, budget 204,800 bytes):** `/` 204,660 and `/find` 169,360
(unchanged); `/c/sample-clinic` 193,726; `/portal` 201,942; `/portal/appointments` 199,296;
`/portal/account` 198,506; `/portal/request` 203,113 (was 200,452).

**Tests.** Unit: `sw.test.ts` runs the real `public/sw.js` in a sandbox (9 cases);
`lib/pwa/manifest.test.ts` (4); `AppPrompts.test.tsx` (7); `AppPromptsGate.test.tsx` (3);
`RegisterServiceWorker.test.tsx` (2); `proxy.test.ts` (1 new). Journey `e2e/pwa.spec.ts` (2). It
runs on full Chromium (`channel: "chromium"`) with `--unsafely-treat-insecure-origin-as-secure`
for the compose origin, because service workers need a secure context and the default headless
shell ignores the flag.

### A11 and the public read limit (12 Nov 2026, developer's decision)

CI failed the discovery journey with a 429 on availability. Every journey shares one address,
and the booking journeys' clinic-page reads (one per doctor) used up the 60 public reads of
that minute. The developer chose:

1. **`PUBLIC_READS_PER_MINUTE`**: an API setting (10–10,000), 60 by default and in production.
   `.env.example`, which CI copies, sets 600. The limiter's 60-a-minute rule keeps its own test
   (`tests/integration/db/test_public_read_limit.py`).
2. **A11 moved from M9 into M7e**: the browser's address reaches the API (ARCHITECTURE §9
   "Client address"). The web proxy strips the two headers from browsers and, with
   `TRUSTED_PROXY_SECRET` and `CLIENT_IP_HEADER`, adds the edge's address and the secret. The
   API trusts it only with that secret. Off by default; M9 configures it for the hosting edge.
   Checked on the real stack with a 10-a-minute limit: two edge addresses had separate budgets,
   and an address sent by the browser itself was ignored.

### E2 — Push subscriptions (12 Nov 2026)

Built as designed; decisions recorded in ADR-0025 and spec `web-push.md` R10–R21.

| Part | Where |
|---|---|
| Domain | `domain/push/subscription.py` (owner, endpoint allow-list, key checks, label, digest), `domain/push/errors.py` |
| Storage | migration `0043`, `adapters/db/models/push.py`, `adapters/db/push.py`; `uow.push_subscriptions` |
| Secrets at rest | `adapters/security/text_cipher.py` (`FernetTextCipher`, the phone-number keys) behind `ports/push.py` `TextCipherPort` |
| Use cases | `application/push/subscriptions.py`: `SubscribeDevice`, `ListDevices`, `RemoveDevice`, `GetPushConfig` |
| HTTP | `delivery/http/push.py`: `/api/v1/push/config`, `/api/v1/portal/push-subscriptions`, `/api/v1/me/push-subscriptions` |
| Preferences | `PUSH` in `Channel` and `PatientChannel`; staff `STAFF_CHANNELS = (IN_APP, PUSH)`; patient `push` field |
| Settings | `VAPID_PUBLIC_KEY` (empty or a 65-byte P-256 point) |
| Contract | 0.52.0: the three paths, `PushConfig`, `PushSubscriptionIn`, `PushDevice`, `PushDeviceList`, `PushError`, `DevicePath`; `PUSH` in both channel enums |

Choices made while building, within the approved design:

- **Owner per person, endpoint by digest.** Unique SHA-256 of the endpoint, so a shared browser
  moves to whoever subscribed last (R14) instead of delivering to two people.
- **Allow-list of push services** (R12), because E3 will POST to the endpoint: anything else is a
  request-forgery path to internal services or cloud metadata.
- **Staff preferences list both channels.** The staff settings screen (web) filters to `IN_APP`
  until E5 adds the push switches, so it shows no duplicates meanwhile.
- **Audit metadata for staff preferences** names push changes `kind:PUSH`. In-app changes keep the
  bare kind, so older rows and their readers are unchanged.

### E3 — Delivery (12 Nov 2026)

Built as designed; rules in spec `web-push.md` R30–R38.

| Part | Where |
|---|---|
| Words | `domain/push/message.py`: fixed title and body per kind (patient EN/HI, staff EN), the path, a tag, the push service's keep time; `waits_for_quiet_hours` |
| Device state | `PushSubscription.mark_sent`, `disable(EXPIRED)` |
| Job | `send_push` (clinic kind, no migration), one per device per notice, key `push:{device}:{sha256(event_key)[:32]}` |
| Enqueue | `application/push/delivery.py` `enqueue_push`, called from `notify_patient` and the staff in-app dispatch (`NotificationService._in_app`) |
| Send | `SendPush`: reads the device, the switch and (staff) the membership again, decrypts, sends, records |
| Port and adapters | `ports/push.py` `WebPushPort`, `PushTarget`, `PushFailure`; `adapters/push/webpush.py` (`pywebpush` 2.5.0) and `adapters/push/console.py`; `bootstrap.build_push` |
| Settings | `PUSH_PROVIDER` (`console` \| `webpush`), `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`; `make config-check` lists them |

Choices made while building, within the approved design:

- **Devices in one query.** A staff notice reads all its recipients' devices at once, and their
  push switches only if someone has a device, so a dispatch's cost stays flat however many
  members are told. `test_a_dispatch_costs_one_query_per_lookup_whatever_the_recipients` now
  expects that one extra lookup (five statements, was four).
- **Quiet hours (R38)** are the reminders' 21:00–08:00 on the clinic's clock. Every kind waits
  except a medicine reminder (the patient's chosen time) and a patient's arrival. The staff
  `KINDS[...].respects_quiet_hours` flag stays false: it describes the in-app notice, which never
  waits (decision 7A, pinned by a test).
- **Prescription and medicine pushes** say only "something new" or "a reminder", because naming
  either is clinical on a lock screen.
- **No redirects, 10-second timeout.** The adapter's HTTP session follows no redirect, so a push
  can reach only the allow-listed host the endpoint names.
- **The VAPID pair is checked at start-up.** A private key from another pair would have every
  push refused (403); the worker stops instead.
- **`pywebpush` brings `aiohttp`** for its async API, which we do not use; `pip-audit` reports no
  known vulnerability in it, `requests`, `py-vapid` or `http-ece`.
- **The service worker does not show pushes yet.** The `push` and `notificationclick` handlers
  come with E5's settings and device test; until then no device can subscribe from the UI.

**Checked on the local stack.** A doctor's device (synthetic endpoint) got one `send_push` job
when the desk booked an appointment at 01:10 IST; it was held until 08:00 IST (`run_at` 02:30
UTC). Brought forward, the worker logged `push.console_sent` (146 bytes, TTL 86,400) and
`push.sent` with the device ID only, and the device's `last_success_at` was set. With
`PUSH_PROVIDER=webpush` in the image, a generated pair built the adapter and a mismatched pair
stopped it with `VAPID_PRIVATE_KEY is not the pair of VAPID_PUBLIC_KEY`.

**Tests.** `tests/unit/domain/test_push_message.py` (every kind, both languages, links, keep
times, quiet hours); `tests/unit/adapters/test_push_adapters.py` (the request decrypted as the
browser would, VAPID header, each status and network failure, no redirects, the pair check,
`build_push`); `tests/integration/test_push_delivery.py` (one job per device, replay, words,
Hindi, both switches, removal and turning off after the notice, 404/410, retries, staff, a bad
job, an unreadable device, night); settings validators.

### E4 — Reminders for app users (13 Nov 2026)

Built as designed; rules in spec `web-push.md` R40–R46.

| Part | Where |
|---|---|
| Who gets reminders | `application/reminders/app.py` `can_remind`: WhatsApp consent **or** an app account linked to the record; used when an appointment is booked and when staff add a follow-up |
| The notice | `remind_in_app`, called by `SendReminder` when a reminder is due, after the appointment and quiet-hours checks: `appointment.reminder` or `follow_up.due` to the linked account, key `{kind}:{reminder_id}` |
| Status | `ReminderStatus.SENT_IN_APP` and `Reminder.sent_in_app`; `sent_for_chain` counts it, so a prescription revision does not remind twice |
| Notice words | `render_title` (EN/HI, names the time or day, doctor and clinic); push words in `domain/push/message.py` |
| Delivery result | `deliver_patient_notice` returns whether the account was reached; `notify_patient` still returns the rows written |
| Migration | `0044`: the two kinds in both kind CHECKs, `SENT_IN_APP` in `ck_reminders_status` |
| Contract | 0.53.0: the two kinds and the status |
| Web | labels for the kinds (EN/HI) and the status (staff "Sent in the app", green, no call prompt; portal EN/HI); the add-reminder hint names the app |

Choices made while building, within the approved design:

- **Reuse the reminder rows** instead of a second schedule: a reminder is one row with one due
  time, so the app notice and the WhatsApp message share timing, quiet hours, deferral and
  cancellation (the "same timing rules" of §3), and nothing new has to follow an appointment.
- **`SENT_IN_APP`** rather than leaving `SKIPPED_NO_CONSENT`: staff would otherwise be told to
  call a patient who was reminded. With both of the patient's switches off for the kind, the
  account is not reached and the status stays `SKIPPED_NO_CONSENT`.
- **Recipient:** the account linked to the record when the reminder is due (R56). An accepted
  booking request links its account, so requested visits are covered. A record linked after
  the booking gets no reminders for that booking (spec §8).
- **Link** `/portal/appointments` for both kinds: a follow-up has no session to request yet, and
  a public doctor page is outside the portal.

**Tests.** `tests/integration/test_app_reminders.py` (7: rows for an app user, the notice and
push once, `SENT_IN_APP`, WhatsApp and the app together, nobody without either, cancellation,
both switches off, a Hindi follow-up allowed and told, still refused without either);
`tests/unit/domain/test_app_reminders.py` (3); migration `0044` round trip; the push-words test
covers the two kinds; web `labels.test.ts` (1). Journeys `patient-notifications`,
`reminders-follow-ups`, `notifications`, `bookings-to-move`, `booking-answers`, `portal-screens`
10/10 on the CI-like stack.

### E5 — Settings, the alert on the screen, docs (13 Nov 2026)

Built as designed; rules in spec `web-push.md` R50–R57. The real-device checks are pending
(AC20 Android with the developer; AC21 iPhone later, none available).

| Part | Where |
|---|---|
| Browser glue | `features/pwa/push.ts`: support (no push, not HTTPS, iPhone outside the installed app), permission, subscribe with the VAPID key (replacing a subscription made under another key), unsubscribe, this device's ID in `localStorage` (`me_push_device`, with its owner) |
| The switch | `features/pwa/DevicePush.tsx`, one component for both sides behind a small `PushApi` |
| Portal | `features/portal/PortalDevicePush.tsx` (loaded with `next/dynamic` when Account renders) and a *Pop-up alert* switch per kind in `PortalAccountPage.tsx` |
| Staff | Settings → Notifications: the device card and a *Pop-up alerts* fieldset beside *In the app* (`NotificationPreferences.tsx`; the E2 `IN_APP` filter is gone) |
| Words | `lib/i18n/push.ts` (EN/HI), apart from the install prompts' words; `patient-notifications.ts` gains `push` |
| Service worker | `public/sw.js`: `push` (the server's words, icon, tag with `renotify`) and `notificationclick` (same-site path only; reuse an open window, else open one) |
| Keys | `make vapid-keys` (`delivery/cli/vapid_keys.py`) |

Choices made while building, within the approved design:

- **"Pop-up alert"** is the word on screen (English and Hindi), not "push".
- **The device card is loaded on demand.** `/portal` prefetches Account's code, and the card's
  code and Hindi words put `/portal` 4 bytes over the 200 KB budget; with `next/dynamic` it is
  202,252 bytes and Account 203,316.
- **No `pushsubscriptionchange` handler.** Renewing a subscription from the service worker would
  need the session's CSRF token, which a worker cannot read. If a browser replaces it, the push
  service answers 410, the device is disabled (R34) and the card shows *Off* until the person
  turns it on again.
- **The journey stubs the push manager and the config** (Q4 A): CI has no VAPID keys and a
  container cannot reach the push services; the device it stores is real.
- **`sw.js` keeps cache `v1`**: the caching rules did not change, so the update replaces the
  worker without throwing away the cached assets.

**Tests.** `sw.test.ts` (6 new: words, fallback, other origins, new window, reused window,
unsteerable window); `DevicePush.test.tsx` (8: on and off, permission only after the press,
expired or moved device, blocked, refused prompt, iPhone, no push or no key, ten devices); the
portal and staff screens (1 each); `test_vapid_keys.py`. Journey `push-settings` (2: a patient
on a phone and a staff member), with `notifications` scoped to *In the app*. Page weights:
`/portal` 202,252, `/portal/account` 203,316, `/portal/appointments` 199,472 bytes.

**Real-device checks.** *(To fill in from RUNBOOK §36 when done.)*
