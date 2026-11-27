#!/usr/bin/env bash
# Look for personal data in the containers' logs (M9-P3; SECURITY_AND_COMPLIANCE "Log review",
# RUNBOOK §42). Run on the VM, or locally against `make up`:
#   bash scripts/log-review.sh            the last 7 days
#   SINCE=24h bash scripts/log-review.sh
#
# It searches each service's log for things shaped like an Indian mobile number, an email address
# or a 12-digit Aadhaar-like number, and prints only counts and the log event that carried them,
# never the matched values: the output is safe to paste into a ticket. Masked values
# (+91******3210, a***@example.com) are not counted. Exit 1 when anything was found.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
COMPOSE="${COMPOSE:-docker compose}"
SINCE="${SINCE:-168h}"

# A phone: +91 or 0 optional, then 10 digits starting 6-9, not inside a longer number or a UUID.
PHONE='(^|[^0-9A-Za-z*-])(\+91|0)?[6-9][0-9]{9}([^0-9A-Za-z-]|$)'
EMAIL='[A-Za-z0-9._%+-]*[A-Za-z0-9_%+-]@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
AADHAAR='(^|[^0-9-])[2-9][0-9]{3} ?[0-9]{4} ?[0-9]{4}([^0-9-]|$)'

found=0
for service in $($COMPOSE config --services); do
  [ "$service" = migrate ] && continue
  logs=$($COMPOSE logs --since "$SINCE" --no-log-prefix "$service" 2>/dev/null) || continue
  [ -n "$logs" ] || continue
  for kind in phone email aadhaar; do
    case $kind in
      phone) pattern=$PHONE ;;
      email) pattern=$EMAIL ;;
      aadhaar) pattern=$AADHAAR ;;
    esac
    # Drop masked values first, so "a***@x" and "+91******3210" are never counted.
    hits=$(grep -E "$pattern" <<<"$logs" | grep -vE '\*\*\*@|\*{4,}[0-9]' || true)
    [ -n "$hits" ] || continue
    found=1
    count=$(wc -l <<<"$hits")
    events=$(grep -oE '"event": ?"[^"]+"' <<<"$hits" | sed -E 's/"event": ?"([^"]+)"/\1/' \
      | sort | uniq -c | sort -rn | head -5 | awk '{printf "%s (%s) ", $2, $1}')
    echo "log-review: $service: $count line(s) with a $kind-like value; events: ${events:-not JSON (e.g. a third-party image)}"
  done
done
if [ "$found" = 0 ]; then
  echo "log-review: nothing phone-, email- or Aadhaar-like in the last $SINCE"
fi
exit "$found"
