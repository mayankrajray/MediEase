# ADR-0021: Directory search in PostgreSQL, over the live tables, behind one rule

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 26 Oct 2026 |
| Deciders | Developer (all M6c design decisions approved in advance, 26 Oct 2026); MediEase engineering |
| Supersedes | — |
| Related | ADR-0003 (tenancy), ADR-0018 (public booking requests), ADR-0020 (applications); spec `docs/specs/discovery.md`; M6c milestone decision M6 |

## Context

M6c-P6 lets a patient find a clinic or a doctor (FR-DIS-01, 02, 04, 05). Search must show **only
what the one discoverability rule allows** (`is_discoverable`: listed, `ACTIVE`, verified, an
address, a verified visible doctor with weekly hours; clinic-onboarding R55), answer in under
500 ms at pilot scale (a few hundred clinics), and rank by relevance, then place, then
availability. No coordinates are stored (milestone decision M6), and every tenant read goes
through a scoped repository (ADR-0003). Milestone decision M6 proposed PostgreSQL with
`pg_trgm` and a *directory read model* (a platform table kept in step with every change).

## Decision

1. **PostgreSQL only, with `pg_trgm`** (migration `0035`, a trusted extension). Words are compared
   with `word_similarity` and `strpos` on lower-cased text; every input is a bound parameter.
2. **No read model yet.** A reviewed cross-clinic reader (`DirectoryReader`,
   `adapters/db/directory.py`) proposes at most 40 candidates from the live tables, reading only
   published columns (a clinic's name, place and specialties; a doctor's name, specialty and
   languages) and returning IDs, a relevance score and a place rank. Each candidate then passes
   the same `load_listing` / `is_discoverable` the owner's screen, the profile and the sitemap
   use, and only public doctors are returned. The rule exists once, in the domain.
3. **Place** is a rank, not a distance: same PIN (0), same city (1), same PIN district — the first
   three digits, India Post's sorting district (2), elsewhere (3). A place filter keeps ranks 0-2.
4. **Availability** ("a free time in the next 7 days") comes from the public page's offer builder,
   without writing sessions, for the candidates only.
5. **Order:** relevance in steps of 0.1, then place, then the earliest free day, then the name.
   At most 20 results; the public read rate limit applies.

## Consequences

- Search can never show what the public page would not, and a change (a suspension, a hidden
  doctor, a registration edit) is visible to search on the next request: there is nothing to
  keep in step.
- Each search runs a few queries per candidate (the listing and the offers). At 40 candidates
  this is well inside the budget for pilot scale; it is **not** a design for thousands of
  clinics.
- **When to revisit:** when listed clinics pass about 2,000, or the p95 of
  `/public/search/*` passes 300 ms, add the directory read model (a platform table refreshed in
  the same transaction as listing, verification, visibility, schedule and suspension changes, and
  rebuilt by a job) with trigram GIN indexes, and keep `is_discoverable` as the check that fills it.
- Rejected: an external search service (one more processor of clinic data, cost, and a second
  copy of the rule); geocoding addresses (a provider, consent wording and accuracy questions for
  little gain at pilot scale); building the read model now (a consistency mechanism to maintain
  before there is load to justify it).
