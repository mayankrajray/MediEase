---
description: Design the next phase before writing any code
argument-hint: <phase id, e.g. M3-P2>
---

Plan phase **$ARGUMENTS** of MediEase. Do not write or change code in this step.

1. Read `TASKS.md` and confirm $ARGUMENTS is the phase marked `▶ ACTIVE`. If it is not, stop and say so.
2. Read the milestone notes in `docs/milestones/` and the spec(s) in `docs/specs/` for this phase.
   If the spec is not `Approved`, list what is missing and stop.
3. Read the relevant ADRs and `docs/ARCHITECTURE.md` sections.
4. Produce the design:
   - What is being built and why (requirement IDs).
   - Concepts I need to understand first, each explained briefly with the trade-off.
   - A request/data flow (Mermaid) if more than one layer is involved.
   - Files to add / modify / delete, grouped by layer.
   - Migrations, contract changes, new error codes, new settings.
   - Tests to write, including failure paths and tenancy isolation.
   - How I will verify the phase (commands + expected output).
   - Risks and open questions.
5. Wait for my approval before implementing.
