# ADR-0024: Stateless assistant turns, signed confirmations, and guard rails on both sides

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 27 Oct 2026 |
| Deciders | Developer (M7 decisions approved in advance, 27 Oct 2026); MediEase engineering |
| Related | ADR-0013 (LLM gateway, which this builds on without editing), ADR-0023 (verified uploads); PRD FR-AI-01..04; spec `assistant.md` |

## Context

ADR-0013 put the model behind a port and said tools wrap existing use cases with the caller's
permissions, writes need a confirmation turn, and guard rails sit before and after the model. It
left open where a conversation lives, how a confirmation is bound to what was proposed, and how
"restate the doctor's instructions" stays a restatement.

## Decision

- **No conversation table.** The browser sends the visible conversation (user and assistant
  text only, at most 20 messages of 2,000 characters) with each turn. Tool calls and tool results
  live only inside one turn on the server and are never accepted from the client, so a client
  cannot forge what a tool returned. A tampered history only changes the caller's own chat.
- **Context is explicit and re-checked every turn.** A prescription is in context only when the
  request names it (`prescription_id` from the portal picker, or `upload_id` of a verified
  upload, ADR-0023); each turn re-authorises it through `PortalScope` or the upload grant.
- **Writes are proposals.** A write tool never runs during a turn: it returns a proposal whose
  summary is written by our code from the resolved arguments, carried in an HMAC-signed token
  bound to the caller (account, or user and clinic), the action, its arguments and a 10-minute
  expiry. `…/assistant/confirm` verifies the token, re-runs the action as the caller (the use case
  re-checks every permission and rule), and accepts each token once.
- **Explanations come from the database.** `explain_prescription` builds plain-language lines
  from the issued version with the phrasebook (the same words as the patient page); the model may
  phrase around them, but a reply about a prescription must use only the numbers present in that
  record, or the deterministic text is returned instead.
- **Guard rails.** Before the model: a request for diagnosis, interpretation of results, dose or
  drug changes or treatment advice (English and Hindi patterns) gets the fixed referral and is
  never sent on. After the model: a reply with advice-like phrasing is replaced by the referral.
  Both are CI-gated tests.
- **Data to the provider.** Staff tool results mask phone numbers. In staging and production a
  real provider is refused unless `LLM_PATIENT_DATA_ALLOWED=true` records that the provider
  contract and the privacy review (SECURITY_AND_COMPLIANCE.md §4) are done; the console adapter
  is refused in production. Logs carry IDs, provider, model, tool names and token counts only.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Store conversations in a table | Server-side history | Stores free text that may be clinical; retention and erasure work | Not needed for one-screen chats |
| Trust the model's confirmation turn ("yes") | Natural | The model decides when a write happens | A write must need an explicit, bound user action |
| Let the model write the whole explanation | Fluent | Can invent a dose | The record must be the only source |

## Consequences

- Positive: no clinical chat text is stored; a write happens only on an explicit confirm bound
  to what was shown; explanations cannot drift from the record.
- Negative: replies about prescriptions are less free-form; a long chat is resent each turn
  (bounded at 20 messages).
- Follow-ups: a provider contract and privacy review before `LLM_PATIENT_DATA_ALLOWED` is set;
  patient-side cancel and reschedule once FR-PRT-08 has use cases.
