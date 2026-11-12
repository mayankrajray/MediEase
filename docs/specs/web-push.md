# Spec: Installable app and web push

| Field | Value |
|---|---|
| Requirements | FR-NTF-01..06 (push channel), NFR-02, NFR-08, NFR-19 |
| Milestone / phases | M7e / E1–E5 (design `docs/milestones/M7e-pwa-push.md`) |
| Status | E1, E2 and E3 Implemented (12 Nov 2026); E4–E5 Approved |
| Owner | Developer |
| Last updated | 2026-11-12 |

## 1. Context
WhatsApp sending is blocked by a Meta Business setting, and patients of small clinics should not
depend on WhatsApp for reminders (design §1). MediEase becomes an installable app (E1) that sends
its own notifications through the browsers' push services (E2–E4), for patients and staff.
Decisions: ADR-0025.

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Anyone | Install the app; read the push config | Subscribe a device |
| A signed-in patient (`@patient`) | Turn push on for this browser, list and remove their devices, choose push per kind | See or remove another account's devices |
| A signed-in staff member (`@authenticated`) | The same for their own devices, in every clinic | See or remove another user's devices |

## 3. Domain model
`PushSubscription` (`domain/push/subscription.py`, table `push_subscriptions`, migration `0043`):
an owner (exactly one of a patient account or a staff user), the endpoint's SHA-256 digest
(unique), the endpoint and keys encrypted, a fixed-vocabulary label, created and updated times, the
last successful send, and `disabled_at` with a reason (`EXPIRED`) set by delivery. No clinic.

## 4. Behaviour

### E1 — Installable app
- **R1** `/manifest.webmanifest` describes one app for staff and patients: start URL and scope
  `/`, standalone, brand colours, 192, 512 and maskable icons.
- **R2** The service worker (`public/sw.js`) caches only `/_next/static/`, `/brand/`, `/icons/`
  and `/offline.html`. It never stores a page or an API answer. API calls and other origins are
  not handled at all.
- **R3** A page that cannot load shows `/offline.html` (English and Hindi, no script). Nothing is
  queued or pretended offline.
- **R4** A new version waits until the person chooses Update.
- **R5** The install offer is shown once per device (Install, Not now and Close are all
  remembered), never inside the installed app. An iPhone gets the Add to Home Screen steps.
- **R6** The manifest link and the registration script are on the staff and portal pages only.
  The landing page, search, clinic and token pages leave them out (NFR-02).

### E2 — Devices and the push channel
- **R10** `GET /api/v1/push/config` (public) says whether push is offered and gives the VAPID
  public key (empty setting: `enabled` false, `public_key` null).
- **R11** A signed-in patient or staff member adds this browser with `PushSubscription.toJSON()`.
  The owner is the session's account or user, never the request.
- **R12** The endpoint must be https on port 443 at a browser push service (`fcm.googleapis.com`,
  `updates.push.services.mozilla.com`, `web.push.apple.com`, `*.push.apple.com`,
  `*.notify.windows.com`), without credentials, at most 2,048 characters. Anything else is 422
  `REQ_VALIDATION_FAILED` naming `endpoint`; the value is never echoed.
- **R13** `keys.p256dh` must be base64url of a 65-byte uncompressed P-256 point and `keys.auth` of
  16 bytes, else 422 naming the key.
- **R14** One browser is one device. The same owner subscribing it again gets 200, the same ID,
  refreshed keys and the device active again. Another person subscribing it gets 201 and takes
  it over; the previous owner no longer lists it.
- **R15** The endpoint and keys are stored only encrypted (the phone-number keys and rotation). The
  API never returns them. The label is from a fixed vocabulary ("Chrome on Android"), never the
  user agent.
- **R16** `GET` lists the caller's own devices, newest first: ID, label, created, last success,
  active.
- **R17** `DELETE /{id}` removes one of the caller's devices (204). Another person's is 404
  `REQ_NOT_FOUND`.
- **R18** Unsafe methods need the CSRF token of the caller's session. A staff session cannot use
  the portal routes and a patient session cannot use the staff routes (401).
- **R19** At most 10 active devices per person (409 `PSH_TOO_MANY_DEVICES`) and 30 subscribe
  calls an hour (429 `PSH_RATE_LIMITED` with `Retry-After`).
- **R20** `PUSH` is a preference channel for every kind, on unless turned off: the patient
  preferences gain `push` beside `in_app` and `email`; staff preferences list an item per kind for
  `IN_APP` and for `PUSH`. Staff may choose only those two channels (409 otherwise). A staff
  change is audited with push changes named `kind:PUSH`.
- **R21** Adding and removing a device are audited (`push_device.added`, `push_device.removed`)
  with the device's ID and label, actor `PATIENT` or `STAFF`, no clinic.

E4 (reminders for app users) and E5 (settings screens and real devices) are added here when they
are built.

### E3 — Delivery
- **R30** Every notice a person is given also goes by push to each of their active devices, as one
  `send_push` job per device, enqueued in the notice's transaction (the outbox). For a patient:
  every kind `notify_patient` delivers, to the linked or requesting account. For staff: every
  in-app kind, to the same recipients (not the member who caused it). The `PUSH` switch is its
  own: push goes with the in-app notice turned off, and stops with push turned off for the kind.
- **R31** The job key is the device and the notice's event key, so a replayed event enqueues
  nothing and a retry for one device never sends again to the others.
- **R32** The push says only fixed words for its kind and the notice's path: never a name, the
  clinic, a doctor, a time, a token, a reason, a medicine or a prescription (those two say only
  that something is new). The body is the JSON `{"title", "body", "url", "tag"}`; `url` is a
  same-site path of at most 200 characters (a patient's always under `/portal`), else the home
  page (`/portal`, `/today`); `tag` is the kind. A medicine due or a patient at the desk is kept
  by the push service for an hour, the rest for a day.
- **R33** A patient's push is in the account's language (English or Hindi); staff's in English.
- **R34** A push service answering 404 or 410 means the browser unsubscribed: the device is
  disabled (`EXPIRED`), the job ends, and later notices skip it. The owner sees it as inactive.
- **R35** At send time the worker reads the device, the switch and (staff) the membership again:
  a device removed or taken over, push turned off, or a member no longer active means nothing is
  sent. A device whose secrets no key can read is skipped.
- **R36** 429, 5xx, a timeout or no connection are retried on the job's backoff
  (`PSH_SERVICE_RATE_LIMITED`, `PSH_SERVICE_UNAVAILABLE`); any other answer, or a redirect, is
  not (`PSH_REFUSED`, the job is dead). An accepted push records the device's last success.
- **R37** Delivery logs the device ID, owner kind and notice kind, never the endpoint, the keys or
  the words. The worker refuses `PUSH_PROVIDER=console` in production, and `webpush` needs the
  VAPID private key that pairs with `VAPID_PUBLIC_KEY` (checked at start-up) and a subject.
- **R38** Quiet hours: a push enqueued between 21:00 and 08:00 clinic time waits until 08:00
  (the in-app notice is there at once). Every kind waits except a medicine reminder (at the time
  the patient chose, 05:00–23:30) and a patient's arrival (only while the clinic is open).
  E4's reminders are timed outside the quiet hours when they are made.

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/push/config` | — | 200 `PushConfig` | — |
| POST | `/api/v1/portal/push-subscriptions` | `PushSubscriptionIn` | 201 or 200 `PushDevice` | 401, 403, 409, 415, 422, 429 |
| GET | `/api/v1/portal/push-subscriptions` | — | 200 `PushDeviceList` | 401, 403 |
| DELETE | `/api/v1/portal/push-subscriptions/{device_id}` | — | 204 | 401, 403, 404 |
| POST, GET, DELETE | `/api/v1/me/push-subscriptions[/{device_id}]` | as above | as above | as above, with `AuthError` |

## 6. UI notes
E1: the install card and the iPhone steps on staff Today and the portal's Home and Account; the
update banner; the offline page. The device switches arrive in E5.

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| A device added (new, or taken over) | `push_device.added` | — (E3: none until a notice) | none |
| A device removed | `push_device.removed` | — | none |
| A device refreshed by its owner | none (logged `push.device_refreshed`) | — | none |
| A notice to a person with devices (E3) | none | `send_push` per active device | none |
| A push service answers 404/410 (E3) | none (logged `push.device_expired`) | — | none |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| Two family members share a phone | The device is the last subscriber's; the other's notices stop on that phone |
| A staff member in two clinics | One device, used for notices from both |
| The account is deleted | Its devices are deleted with it (cascade) |
| An endpoint at an internal address | 422 before anything is stored |

## 9. Acceptance criteria
- **AC1 (R2)** — Given the app has been opened, then the cache holds only build assets, logos,
  icons and the offline page (journey `pwa`).
- **AC2 (R3)** — Given the network is off, when a page is opened, then the offline page shows at
  360 px and passes axe (journey `pwa`).
- **AC3 (R11, R15)** — Given a patient subscribes, then the row holds no readable endpoint or key.
- **AC4 (R14)** — Given another account subscribes the same browser, then it moves to them.
- **AC5 (R17, NFR-08)** — Given another person's device ID, then delete is 404 and the device
  stays.
- **AC6 (R12)** — Given an endpoint at `169.254.169.254`, then 422 and nothing is stored.
- **AC7 (R30, R31)** — Given a patient with two devices and an accepted request, then two
  `send_push` jobs, and a replay of the event adds none (`test_push_delivery.py`).
- **AC8 (R32, R33)** — Given those jobs run, then each device is handed the fixed words, with no
  clinic, doctor or patient name, and a Hindi account gets the Hindi words.
- **AC9 (R34)** — Given the push service answers 410, then the device is disabled and the next
  notice enqueues nothing for it.
- **AC10 (R36)** — Given 429 or 503, then the job is retried; given 403, then it is dead.
- **AC11 (R32)** — Given the pywebpush adapter, then the request is encrypted for the browser (the
  test decrypts it as the browser would), signed with VAPID, and never follows a redirect.
- **AC12 (R38)** — Given a cancellation at 23:30 clinic time, then its push runs at 08:00; a
  medicine reminder's runs at once.

## 10. Observability
Logs `push.device_added` (owner kind, device ID, moved), `push.device_refreshed`,
`push.device_removed`, `push.rate_limited`; from E3 `push.sent`, `push.skipped` (reason
`no_device`, `turned_off`, `not_a_member`, `unreadable`), `push.device_expired`, `push.failed`
(code, status) and `notification.dispatched` `push_devices`; never the endpoint, keys, words or
user agent. Error codes `PSH_TOO_MANY_DEVICES`, `PSH_RATE_LIMITED`, `REQ_VALIDATION_FAILED`,
`REQ_NOT_FOUND`; job codes `PSH_SERVICE_RATE_LIMITED`, `PSH_SERVICE_UNAVAILABLE`, `PSH_REFUSED`.

## 11. Out of scope
Native apps; SMS as a paid fallback; offline clinical data; a third-party push provider.

## 12. Open questions
None.
