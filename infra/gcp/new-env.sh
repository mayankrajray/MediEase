#!/usr/bin/env bash
# Write the VM's .env from infra/gcp/env.production.example with fresh internal secrets
# (M9-P1; RUNBOOK §38). Run once, in /opt/mediease: bash infra/gcp/new-env.sh
# Refuses to overwrite an existing .env. Prints no secret; lists the values left to fill.
set -euo pipefail
umask 077
cd "$(dirname "$0")/../.."

[ -e .env ] && { echo "new-env: .env already exists; nothing changed" >&2; exit 1; }
command -v openssl > /dev/null || { echo "new-env: openssl is needed" >&2; exit 1; }

# URL-safe, no padding: safe inside sed and connection strings.
secret() { openssl rand -base64 48 | tr -d '\n=' | tr '+/' '-_'; }
# A Fernet key: 32 random bytes, URL-safe base64 (with its padding).
fernet() { openssl rand 32 | base64 | tr -d '\n' | tr '+/' '-_'; }

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
cp infra/gcp/env.production.example "$tmp"
password=$(openssl rand -hex 24)
sed -i "s/__POSTGRES_PASSWORD__/$password/g" "$tmp"
sed -i "s/__FERNET__/$(fernet)/" "$tmp"
while grep -q '__GENERATE__' "$tmp"; do
  sed -i "0,/__GENERATE__/s//$(secret)/" "$tmp"
done
install -m 600 "$tmp" .env

echo "new-env: wrote .env (owner-only) with new internal secrets."
echo "new-env: still to fill (nano .env):"
grep -E '^[A-Z_]+=$' .env | cut -d= -f1 | sed 's/^/  /'
