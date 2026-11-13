#!/usr/bin/env bash
# The restore drill (M9-P1 C4; RUNBOOK §39): restore a database backup into a scratch database
# beside the live one, compare row counts, and drop the scratch database. The live database is
# only read.
#
# Usage on the VM:
#   sudo scripts/restore-check.sh                      # the newest backup in the bucket
#   sudo scripts/restore-check.sh db-20261114T213000Z.dump
#   sudo scripts/restore-check.sh ./db-20261114T213000Z.dump   # a local file
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

if [ -z "${BACKUP_BUCKET:-}" ] && [ -f .env ]; then
  BACKUP_BUCKET=$(sed -n 's/^BACKUP_BUCKET=//p' .env | tail -1 | tr -d '"'"'"' \r')
fi
COMPOSE="${COMPOSE:-docker compose}"
SCRATCH="restore_check"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

choice="${1:-}"
if [ -n "$choice" ] && [ -f "$choice" ]; then
  cp "$choice" "$work/backup.dump"
else
  : "${BACKUP_BUCKET:?set BACKUP_BUCKET (the bucket name) in .env}"
  if [ -z "$choice" ]; then
    choice=$(gcloud storage ls "gs://$BACKUP_BUCKET/db/" | sort | tail -1)
    choice=${choice##*/}
  fi
  [ -n "$choice" ] || { echo "restore-check: no backup found in gs://$BACKUP_BUCKET/db/" >&2; exit 1; }
  echo "restore-check: fetching $choice"
  gcloud storage cp --quiet "gs://$BACKUP_BUCKET/db/$choice" "$work/backup.dump"
fi

psql_db() { $COMPOSE exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d $1 -v ON_ERROR_STOP=1 -qAt -c \"$2\""; }
live_db='"$POSTGRES_DB"'

started=$(date +%s)
psql_db postgres "DROP DATABASE IF EXISTS $SCRATCH"
psql_db postgres "CREATE DATABASE $SCRATCH"
$COMPOSE exec -T db sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $SCRATCH --no-owner --exit-on-error" \
  < "$work/backup.dump"
took=$(( $(date +%s) - started ))

echo "restore-check: restored in ${took}s; row counts (live / restored):"
status=0
for table in clinics users patients appointments visits prescriptions bills payments audit_events alembic_version; do
  live=$(psql_db "$live_db" "SELECT count(*) FROM $table")
  restored=$(psql_db "$SCRATCH" "SELECT count(*) FROM $table")
  mark="ok"
  # Rows written since the backup make the live count larger, never smaller.
  if [ "$restored" -gt "$live" ]; then mark="CHECK"; status=1; fi
  printf '  %-16s %8s / %-8s %s\n' "$table" "$live" "$restored" "$mark"
done
version=$(psql_db "$SCRATCH" "SELECT version_num FROM alembic_version")
echo "restore-check: the backup's schema is at migration $version"
[ -n "$version" ] || status=1
psql_db postgres "DROP DATABASE $SCRATCH"
echo "restore-check: scratch database dropped"
exit $status
