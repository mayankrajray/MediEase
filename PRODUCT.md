# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Clinic owners and administrators** of small independent clinics in India. They decide to buy
  and pay (confirmed by the developer, 9 Nov 2026).
- **Doctors**: daily users and strong influencers on the purchase. They see patients, write
  prescriptions and run their own schedule.
- **Front desk staff (receptionists)**: the heaviest daily users, at a 1366×768 screen with a
  keyboard, managing the day's appointments and queue.
- **Patients and their family members**: on a phone, often low-end Android, reading in English or
  Hindi; they open prescription links, book, and use the patient portal and its assistant.
- **MediEase operations staff**: onboard and verify clinics in the ops console.

## Product Purpose

MediEase runs a small clinic's day in one place: booking and the daily queue, patient records,
visits and digital prescriptions, WhatsApp reminders and prescription links, billing, and an
assistant that books and explains prescriptions. Success is a front desk that keeps the day
moving without paper or phone tag, and patients who know when to come and how to take their
medicines.

## Positioning

WhatsApp-native and built for Indian small clinics: patients get their prescription, reminders and
booking on WhatsApp in English or Hindi without installing an app; the clinic works from one
screen. The assistant restates only what the doctor wrote and never gives medical advice.

## Operating Context

- The surfaces partners use most: the **clinic dashboard**, especially **appointment management**,
  **patient records** and the **daily appointment and queue view** (developer, 9 Nov 2026).
- Clinic screens are used for hours a day at the front desk; speed and keyboard use matter more
  than decoration.
- Patient pages open from a WhatsApp link on a phone, often on a slow connection.

## Capabilities and Constraints

- Web app: Next.js (App Router) and Tailwind 4 over a Flask API; the API is the authority for every
  rule. A redesign changes presentation only.
- Patient pages: mobile first, readable at 360 px, under 200 KB first-load transfer, no analytics
  SDKs, no clinical text in titles or URLs.
- WCAG 2.1 AA everywhere; status never shown by colour alone.
- English and Hindi on patient-facing surfaces; clinic screens are English.
- Strict, nonce-based CSP: no third-party scripts, fonts or images.

## Brand Commitments

- Name: MediEase. Logo files in `apps/web/public/brand/` (emblem: teal cross with a person and a
  mint leaf; colours `#147D72`, `#DDF3EE`, `#172B35`).
- Direction chosen by the developer: Modern Healthcare SaaS (calm, light, trustworthy).
- Voice: plain, specific, calm; no exclamation marks.

## Evidence on Hand

- Design partners use the product (developer, 9 Nov 2026), but **partner names, logos,
  testimonials and quotations must not be published** without their explicit permission. Landing
  and marketing surfaces show product features and benefits only.
- Prices come from the plans already in the product (`src/lib/i18n/landing.ts`); no invented
  numbers, customer counts or statistics.

## Product Principles

1. The front desk's next action is always one click away.
2. Say what happened and what to do next, in the user's language.
3. Never imply clinical advice; restate only what the doctor wrote.
4. Light on the patient's phone and data plan.
5. One coherent product: every screen follows the same design system.

## Accessibility & Inclusion

WCAG 2.1 AA (axe in the Playwright journeys); 24 px minimum targets (44 px on patient pages);
reduced motion respected; Hindi in Devanagari on patient surfaces.
