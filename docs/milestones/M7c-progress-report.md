# M7c progress report

| Field | Value |
|---|---|
| Milestone | M7c — Demo polish, real configuration and Phase 2 deliverables (issue #69) |
| Branch | `m7c/69-demo-polish` (local; not pushed yet) |
| Design | `docs/milestones/M7c-demo-polish.md` (decisions D1–D16) |
| Report date | 9 Nov 2026 |
| Phase 2 deadline | 15 Nov 2026, 11:59 PM IST: **6 days from this report** |

## 1. What is done

| Phase | Status | What changed for the user | Commit |
|---|---|---|---|
| Plan | ✅ | M7c opened; L-09, L-10, L-11 marked done; spec rules R15–R21 | `56a646d` |
| **P3** Staff booking | ✅ | The staff assistant offers only sessions and times that can still be booked (no 3:55 AM after it ended, no full sessions), refuses an ended one before the confirmation card, asks which doctor when the clinic has several, and knows tomorrow's date | `5138f16` |
| **P1** Doctor's advice | ✅ | "Is there any other advice that doctor mentioned in the prescription?" now answers with the doctor's own advice (food, rest, precautions) instead of a refusal. Advice of the assistant's own is still refused | `1c790f3` |
| **P2** Hinglish | ✅ | "doctor ne kya likha hai", "kal ka appointment chahiye" are understood; Hinglish advice requests ("kya main do goli le lu") are still referred to the clinic | `1c790f3` |
| **P5** Providers | ✅ | `LLM_PROVIDER=mistral` or `nvidia` switches the model; nothing else changes | `f4f49fd` |
| **P6** Real configuration | ◐ agent's part done | `make config-check` shows what each service uses without printing a secret; `LIVE=1` tests each one; `EMAIL_TO=` / `WHATSAPP_TO=` send one test | `152f927` |
| **P4** Formatting | ✅ | Bold, lists and numbered medicines show as formatted text; links and HTML never render | `7f4578b` |
| P7 Redesign | ☐ waiting for you | — | — |
| P8 Rehearsal and deliverables | ☐ | — | — |

### Checks run
- API: lint (ruff), layer boundaries (import-linter, 5 contracts kept), mypy (435 files) clean.
  The assistant, guard-rail, LLM adapter and config-check suites pass (P3 8 new tests, P1/P2 30 new
  guard-rail cases and 3 HTTP tests, P5 4 new tests, P6 7 new tests). The full suite with the
  coverage gates passed (§4).
- Web: ESLint and `tsc` clean; the assistant tests pass (4 new).
- Your real services, by `make config-check LIVE=1` on 9 Nov 2026:

  | Service | Result |
  |---|---|
  | Email (Brevo) | ok: logged in to smtp-relay.brevo.com |
  | Google sign-in | ok: Google reachable (the client is proved by a real sign-in) |
  | Model (Groq, `openai/gpt-oss-120b`) | ok: answered |
  | WhatsApp | not tested: `MESSAGING_PROVIDER` is still `console` |

## 2. What I need from you

### To finish P6 (real configuration)
1. **WhatsApp.** In `.env` set `MESSAGING_PROVIDER=whatsapp_cloud` and the four values
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN` (a permanent system-user token, not the
   24-hour one), `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` (any random 16+ characters), then
   `make up`. Tell me when it is done; I will run `make config-check LIVE=1`, then send the
   `hello_world` template to a number you give me (`WHATSAPP_TO=`). For delivery statuses and STOP
   to flow back, Meta needs a public webhook: locally a tunnel (`cloudflared tunnel --url
   http://localhost:8000`), registered as `<tunnel>/webhooks/whatsapp` with your verify token and
   subscribed to `messages`; after deployment, the deployed API URL instead.
2. **Email sender.** `EMAIL_FROM` is a Gmail address. Sent through Brevo it fails Gmail's DMARC
   check, so emails may be rejected or land in spam. Use an address on a domain you verified in
   Brevo (SPF, DKIM, DMARC), or at least test with `make config-check EMAIL_TO=<your address>` and
   check the spam folder. Tell me the result.
3. **Google sign-in.** Click *Continue with Google* on `http://localhost:3000` once and tell me
   whether it signs you in. After deployment, add `<deployed URL>/api/v1/auth/google/callback` as
   a redirect URI in the Google Cloud OAuth client.
4. **The model.** You use Groq with `openai/gpt-oss-120b`. To try the others, set
   `LLM_PROVIDER=mistral` (key from console.mistral.ai) or `LLM_PROVIDER=nvidia` (an `nvapi-` key
   from build.nvidia.com), leave `LLM_MODEL` empty for the default or name one, `make up`, and run
   `make config-check LIVE=1`.
5. **The deployment link**, when you have it. Until then every link is `localhost`, listed in
   `deliverables/PLACEHOLDERS.md` (local only, never committed).

### To start P7 (landing page and frontend redesign)
1. **The modules to redesign**, in priority order (for example: landing page, sign-in, clinic
   dashboard and queue, booking drawer, patient portal, assistant, billing).
2. **The design sources, made available to me:**
   - `ai-design-skills`: the exact GitHub repository URL, so I install it into `.kiro/skills/` and
     use its `landing-page-design.md`.
   - Mobbin: its MCP server entry for `.kiro/settings/mcp.json` (you add it; I cannot write that
     folder) and your Mobbin account or API key if it needs one.
   - Impeccable design system, Watermelon UI, Skiper UI, Aceternity UI, Animaster: confirm the
     exact sites or packages you mean. I will check each component's licence before copying it,
     and rebuild paid templates (Modulify, Landdding, Recent) as our own code rather than copy them.
   - The "Ponytail" plugin: its link, or confirm I should skip it.
3. **Brand:** the official MediEase logo (still a placeholder on the prescription PDF), the
   colours and fonts to keep or change, and one or two sites whose look you want.
4. **Permission to study practo.com with REA:** public pages only, no sign-in, nothing copied.
5. **Patient pages' limit:** confirm the 200 KB budget for the prescription link and booking page
   stays. Heavy animation then goes on the landing page and the clinic dashboard only.

### Before the Phase 2 submission (from the brief)
The brief requires design partners to have used the deployed product in at least 2 of the 3
weeks before 15 Nov (that is, from 25 Oct). With 6 days left, that window can only be met by usage
that has already started; tell me whether partners are using it today, because it decides what
the deliverables can honestly claim.

These come from real events, so I leave them as placeholders and never write them:
partner confirmations, partner usage, partner quotes for the feedback log, the pricing
conversation and its objections, and the post-mortem's answers. The deployment is the most urgent
item.

## 3. Known gaps
- Partner-side use of the assistant on real patients needs the privacy review (L-04) and
  `LLM_PATIENT_DATA_ALLOWED=true`; until then demo it on the reviewer clinic only.
- `make e2e` adds short extra sessions at the time it runs; never run it against demo or partner
  data (RUNBOOK §35).
- The usage-evidence export per clinic (account creation, active users, records, weekly activity)
  is planned for P8.

## 4. Full suite (9 Nov 2026, on the branch at `7f4578b`)

| Check | Result |
|---|---|
| `make test-api` | 2,573 passed in 34 min; package coverage 96.05% (gate 90%), `domain/` + `application/` 95% (gate 80%) |
| `make test-web` | 87 files, 726 tests passed |
| `make lint typecheck` (API and web) | clean |
| Assistant journeys (`assistant.spec.ts`) | 2 passed, with the API on the console model and fake Google sign-in as in CI (RUNBOOK §35); with your real Google sign-in and Groq they cannot pass, by design |

With your real Groq model, the staff assistant answered "show today's queue" with a formatted
list of today's sessions (seen during the journey run), so P4's formatting works on real replies.
