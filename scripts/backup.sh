#!/usr/bin/env bash
# Back up the database and the stored files to the private Cloud Storage bucket (M9-P1 C4;
# RUNBOOK §39). Run on the production VM by the mediease-backup timer (infra/gcp/), nightly, or by
# hand: sudo scripts/backup.sh
#
# - The database: pg_dump in PostgreSQL's custom format (compressed; restored with pg_restore).
# - The files: the `blobs` volume (prescription PDFs, quarantined uploads) as a tar.gz.
# - Uploaded with the VM's own service account (gcloud on Google's Ubuntu images); no key file.
#   The bucket deletes objects after 30 days (its lifecycle rule).
# - Written with umask 077 to a private temporary directory and removed after the upload.
#
# Needs BACKUP_BUCKET (the bucket name, without gs://), from the environment or .env.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

if [ -z "${BACKUP_BUCKET:-}" ] && [ -f .env ]; then
  # Only this one setting is read from .env; nothing else is loaded or printed.
  BACKUP_BUCKET=$(sed -n 's/^BACKUP_BUCKET=//p' .env | tail -1 | tr -d '"'"'"' \r')
fi
: "${BACKUP_BUCKET:?set BACKUP_BUCKET (the bucket name) in .env}"

COMPOSE="${COMPOSE:-docker compose}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "backup: database"
# The container's own POSTGRES_* variables name the user and database; no password is needed
# over the local socket.
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6' \
  > "$work/db-$stamp.dump"
[ -s "$work/db-$stamp.dump" ] || { echo "backup: the database dump is empty" >&2; exit 1; }

echo "backup: files"
# Through the API container, which mounts the volume: no other image is needed.
$COMPOSE exec -T api tar -czf - -C /var/lib/mediease/blobs . > "$work/blobs-$stamp.tar.gz"

echo "backup: upload to gs://$BACKUP_BUCKET/"
gcloud storage cp --quiet "$work/db-$stamp.dump" "gs://$BACKUP_BUCKET/db/db-$stamp.dump"
gcloud storage cp --quiet "$work/blobs-$stamp.tar.gz" "gs://$BACKUP_BUCKET/blobs/blobs-$stamp.tar.gz"

echo "backup: done ($(du -h "$work/db-$stamp.dump" | cut -f1) database, $(du -h "$work/blobs-$stamp.tar.gz" | cut -f1) files)"
