# ADR-0013: An LLM gateway behind a port, OpenAI-compatible, Groq first

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-20 |
| Deciders | Developer (product owner), engineering agent |
| Related | PRD v1.1 C4, FR-AI-01..03; ADR-0007 (the same port-and-adapter pattern for messaging); SECURITY_AND_COMPLIANCE.md §4 |

## Context

PRD v1.1 adds an assistant (M7) that books by chat, answers clinic questions and restates the
doctor's own instructions, through tools. The project has no budget: the first provider must have
a free tier, and switching to a paid one later (DeepInfra, OpenAI) must not mean rewriting code.
Groq, DeepInfra and OpenAI all serve the OpenAI chat-completions API with tool calling at a
configurable base URL (Groq: `https://api.groq.com/openai/v1`; DeepInfra:
`https://api.deepinfra.com/v1/openai`). Free tiers have low rate limits (Groq's is reported at
about 30 requests a minute) and their data terms may allow use of inputs.

## Decision

- An `LlmPort` in `ports/` with one call: messages (system, user, assistant, tool results) and
  tool definitions in, a reply or tool calls out, plus token usage. Nothing outside the adapter
  knows the provider.
- One adapter, `OpenAICompatibleLlm`, over HTTP (stdlib, as the WhatsApp adapter, or the `openai`
  SDK if tool-call parsing justifies the dependency at M7-P1). Provider, base URL, model, key,
  timeout and limits are settings: `LLM_PROVIDER` (`groq`, `deepinfra`, `openai`, `console`),
  `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`. A `console` adapter answers from a script for tests
  and offline demos.
- Tools are thin wrappers over existing use cases, called with the signed-in person's own context,
  so the model can never reach more than the person could through the API. Writes (book,
  reschedule, cancel) need an explicit confirmation turn.
- Guard rails before and after the model: clinical questions (diagnosis, drugs, doses, results)
  get a fixed referral to the clinic and are never sent on; the system prompt forbids medical
  advice; tool results carry only what the screen would show. Guard-rail tests are a CI gate.
- Until a provider with suitable data terms is contracted, only synthetic data is sent (local and
  demo). Every call is logged with IDs, provider, model and token counts, never the text.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Call Groq's SDK directly | Fewest lines | Provider spread through the code; switching means a rewrite | FR-AI-03 asks for a setting, not code |
| A third-party gateway (LiteLLM, OpenRouter) | Many providers at once | Another service or dependency and its data path; more than M7 needs | Revisit if we need routing or fallback across providers |
| A local model | No data leaves | No free host can run one usefully | Not feasible on this budget |

## Consequences

- Positive: switching provider is a settings change; tests run without a network; the assistant
  cannot exceed the user's permissions.
- Negative / costs: free-tier limits mean the demo must handle `LLM_RATE_LIMITED` gracefully;
  OpenAI-compatible is not identical everywhere (tool-call details differ slightly), so each new
  provider gets a short compatibility test.
- Follow-ups and triggers to revisit: a provider contract and a privacy review before any real
  patient data is sent (SECURITY_AND_COMPLIANCE.md §4); a multi-provider fallback if outages hurt.
