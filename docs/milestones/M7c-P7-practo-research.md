# Practo UX research (M7c-P7, 9 Nov 2026)

Public pages only (`https://www.practo.com/`), with the developer's permission, read through REA
(`inspect_web_page`, accessibility tree; no sign-in, no clicks, no data). Nothing was copied: the
notes below describe patterns in our words. Evidence ID: `ev_fa1096a0…`.

## What the page does

- **Patient-first, search-first.** The first screen is a location and search pair, then a row of
  four service tiles, each a short title with a one-line promise ("find doctors near you",
  "confirmed appointments").
- **Concern-led entry.** A grid of plain-language concerns ("cold, cough or fever", "child not
  feeling well"), each with one action, instead of medical speciality names.
- **Proof** through user testimonials and a health-articles strip.
- **App push**: a phone-number field to text a download link.
- **A large footer** of grouped links (patients, doctors, company, legal, social).

## What MediEase takes from it (rebuilt independently)

| Pattern | Use in MediEase | Where |
|---|---|---|
| Short service tiles: a title and one promise line each | The benefit cards on the landing page | M1 |
| Plain words before medical terms | Feature and FAQ copy in everyday words; the directory search accepts everyday words | M1, M6 |
| Search as the first action for patients | "Find a doctor" stays the patient path's first action | M1, M7 |
| Grouped footer | A footer grouped by audience (clinics, patients) with only working links | M1 |

## What MediEase does not take

- Testimonials and logos: none are published without a partner's permission (PRODUCT.md).
- Health articles and symptom-led prompts ("performance issues", "depression"): MediEase gives no
  health information and never suggests care (principle "trust over convenience").
- An app-download push: patients use links and the web portal; no app to install.
- A dense, many-option first screen: one primary action per audience (Hick's law).
