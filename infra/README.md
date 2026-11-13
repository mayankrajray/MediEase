# infra

Deployment configuration for production (ADR-0009, ADR-0026).

## gcp/ — one Compute Engine VM (M9-P1)

| File | What it is |
|---|---|
| `docker-compose.prod.yml` | Layered on the root `docker-compose.yml` through `COMPOSE_FILE` in the VM's `.env`: Caddy on 80/443, no other published port, log rotation, Mailpit off |
| `Caddyfile` | TLS for `PUBLIC_HOST` (Let's Encrypt), HSTS, a request size cap, the proxy to the web app |
| `env.production.example` | Every production setting by name, with the fixed values; no secret |
| `new-env.sh` | Writes the VM's `.env` from that file with new internal secrets (owner-only) |
| `mediease-backup.service`, `.timer` | The nightly backup (`scripts/backup.sh`) as a systemd timer |

How to deploy, update, roll back, back up and restore: `docs/RUNBOOK.md` §38 and §39.
