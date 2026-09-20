# Security Policy

MediEase stores patient health information on behalf of clinics. Security reports are handled
with priority.

## Reporting a vulnerability

- Email: **security@mediease.example** *(replace with the real address before launch)*
- Do not open a public issue for a vulnerability.
- Include: affected URL or component, steps to reproduce, impact, and any request IDs.
- We acknowledge within 2 business days and share a remediation plan within 7 days.

## Scope

In scope: the web app, the API, patient links, webhooks, and the ops console.
Out of scope: denial-of-service volume testing, social engineering, third-party providers
(report those to the provider).

## Handling rules for contributors

- Secrets live only in environment variables or the deployment secret store. Never in code,
  images, logs, issues or AI prompts.
- If a secret is exposed, rotate it immediately, then follow `docs/RUNBOOK.md` → "Secret exposure".
- If patient data may have been exposed, follow `docs/RUNBOOK.md` → "Suspected data breach" —
  the affected clinic must be informed without delay.

Controls and compliance mapping: [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md).
