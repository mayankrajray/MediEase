#!/usr/bin/env bash
# How long a clinic's onboarding took, from its checklist (M9-P5; FR-OPS-04, goal G4; RUNBOOK §44).
#   make onboarding-report SLUG=<clinic-slug>
#
# Each step's first time is written once by the app (never overwritten), so this reads facts,
# not a stopwatch: minutes from the start of the ops wizard to each step, and the total to the
# first prescription. Prints the clinic's slug, times and counts only.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
COMPOSE="${COMPOSE:-docker compose}"
SLUG="${1:?usage: scripts/onboarding-report.sh <clinic-slug>}"
[[ "$SLUG" =~ ^[a-z0-9-]{2,64}$ ]] || { echo "onboarding-report: not a clinic slug" >&2; exit 2; }

# The slug is checked above, so it can be placed in the query as a literal.
$COMPOSE exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1 -q -P footer=off" <<SQL
\\pset null '-'
WITH c AS (
  SELECT o.* FROM onboarding_checklists o JOIN clinics k ON k.id = o.clinic_id
  WHERE k.slug = '$SLUG'
), steps(step, at, n) AS (
  SELECT 'wizard started', started_at, 1 FROM c
  UNION ALL SELECT 'clinic created', clinic_created_at, 2 FROM c
  UNION ALL SELECT 'doctors added', doctors_added_at, 3 FROM c
  UNION ALL SELECT 'staff invited', staff_invited_at, 4 FROM c
  UNION ALL SELECT 'patients imported', patients_imported_at, 5 FROM c
  UNION ALL SELECT 'first appointment', first_appointment_at, 6 FROM c
  UNION ALL SELECT 'first prescription', first_prescription_at, 7 FROM c
)
SELECT step,
       to_char(at AT TIME ZONE 'Asia/Kolkata', 'DD Mon HH24:MI') AS "time (IST)",
       round(extract(epoch FROM at - (SELECT started_at FROM c)) / 60) AS "minutes from start"
FROM steps ORDER BY n;
WITH c AS (
  SELECT o.* FROM onboarding_checklists o JOIN clinics k ON k.id = o.clinic_id
  WHERE k.slug = '$SLUG'
)
SELECT CASE
  WHEN NOT EXISTS (SELECT 1 FROM c) THEN 'no such clinic, or it was not made with the ops wizard'
  WHEN (SELECT first_prescription_at FROM c) IS NULL THEN 'not finished: no prescription yet'
  ELSE 'total ' || round(extract(epoch FROM (SELECT first_prescription_at - started_at FROM c)) / 60)
       || ' minutes; target under 60 (G4) '
       || CASE WHEN (SELECT first_prescription_at - started_at FROM c) < interval '60 minutes'
               THEN 'MET' ELSE 'NOT MET' END
END AS result;
SQL
