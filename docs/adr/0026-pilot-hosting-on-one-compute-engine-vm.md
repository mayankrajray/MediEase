# ADR-0026: The pilot runs on one Compute Engine VM with Docker Compose, PostgreSQL included

| Field | Value |
|---|---|
| Status | Accepted (M9-P1, 13 Nov 2026) |
| Date | 2026-11-13 |
| Deciders | Developer (Google Cloud assessment approved 13 Nov 2026); agent |
| Related | ADR-0009 (Docker everywhere, India region), ADR-0012 (blob storage), ADR-0005 (job queue); design `docs/milestones/M9-deploy-demo.md`; RUNBOOK §38, §39 |

## Context

The Phase 2 deliverables need a public HTTPS address by 15 Nov 2026, kept working until
31 Mar 2027, for the demo video, the mentor and three design partners. The money available is a
Google Cloud Free Trial credit of ₹28,569 until 12 Feb 2027, then a paid account. Oracle Cloud
(card refused) and Railway (30-day trial, 1 GB per service, SMTP blocked) were ruled out.
ADR-0009 assumed managed PostgreSQL with point-in-time recovery and images built in CI.

Two shapes were compared in the assessment: one VM running the whole compose stack (A), and a VM
with Cloud SQL (B). B costs about ₹26,000–28,600 for 90 days against about ₹19,700 for A, needs
connection and TLS changes for the database, and could not be ready in two days.

## Decision

1. **One e2-standard-2 VM** (2 vCPU, 8 GB), Ubuntu 24.04 x86_64, asia-south1, a static IPv4,
   running the existing `docker-compose.yml` with `infra/gcp/docker-compose.prod.yml` layered on
   by `COMPOSE_FILE` in the VM's `.env`. Images are built on the VM from the reviewed commit.
2. **PostgreSQL 16 stays in Docker** on the VM's disk. Backups: a nightly `pg_dump` (custom
   format) and a tar of the files volume to a private Cloud Storage bucket with a 30-day
   lifecycle, written with the VM's own service account (no key file), plus a daily disk
   snapshot kept 7 days. `scripts/restore-check.sh` is the restore drill.
3. **Caddy** terminates TLS (Let's Encrypt, renewed by itself) on `PUBLIC_HOST`
   (`mediease.duckdns.org`, then `mediease.care`), adds HSTS and forwards to the web app; the
   browser talks to one origin (ADR-0006). Only ports 80 and 443 are published; SSH only through
   Google's IAP range.
4. **Uploaded files stay on the VM disk** (`BLOB_STORAGE=local`) for now. Cloud Storage's
   S3-compatible API does not honour `If-None-Match` on uploads, so the S3 adapter's write-once
   guarantee would silently weaken there; a Cloud Storage adapter using `if_generation_match=0`
   comes later.
5. **Messaging is off** (`MESSAGING_PROVIDER=disabled`) until Meta allows sending.

## Consequences

- Cheap and identical to the local stack, so what was tested is what runs.
- One VM in one zone is a single point of failure; recovery is from the snapshot or the dumps,
  measured by the restore drill. Point-in-time recovery is not available (up to a day of data can
  be lost).
- Patching the OS (unattended upgrades) and the images (Dependabot, rebuild on deploy) is ours.
- The Free Trial is a hard spending cap: when the credit or the 90 days run out, Google stops the
  resources and charges nothing. Before 12 Feb 2027 the account is upgraded to paid to stay live.
- Moving to Cloud SQL later is a `DATABASE_URL` change plus a dump and restore.
