#!/usr/bin/env bash
# The production watch (M9-P2; RUNBOOK §41). Run on the VM every 5 minutes by the mediease-watch
# timer (infra/gcp/), or by hand to see what it finds: make watch (sends nothing, changes nothing).
#
# Each run checks the stack and emails OPS_ALERT_EMAIL (through the API image's ops_alert command)
# only when something changes: a new problem, a problem that cleared, or once a day while one
# lasts. "critical" problems (the site is down) are sent at any hour; "warning" ones only from
# 08:00 to 22:00 India time and are held until then. The email carries service names, counts and
# error codes only, never patient data (NFR-07).
#
# Checks (thresholds from the environment or WATCH_* lines in .env):
#   containers  a service of the stack is not running, or unhealthy   (critical for db, api, web,
#                                                                       caddy; warning otherwise)
#   errors      >= WATCH_5XX_THRESHOLD (5) server errors in the API log in the last 5 minutes
#   jobs        dead jobs in 24 h; a running job stuck; the oldest due job waiting more than
#               WATCH_QUEUE_AGE_SECONDS (600)
#   backup      the backup service failed, or no successful backup in 26 hours
#   disk        the root disk over WATCH_DISK_PERCENT (85) % full
#   certificate the site's certificate ends in under WATCH_CERT_DAYS (14) days
#
# State is kept in $WATCH_STATE_DIR (systemd's StateDirectory, /var/lib/mediease-watch). If the
# email cannot be sent the state is not changed, so the next run tries again.
set -uo pipefail
umask 077
cd "$(dirname "$0")/.." || exit 1

COMPOSE="${COMPOSE:-docker compose}"
ENV_FILE="${WATCH_ENV_FILE:-.env}"
STATE_DIR="${WATCH_STATE_DIR:-${STATE_DIRECTORY:-/var/lib/mediease-watch}}"
STATE="$STATE_DIR/state.tsv"
DRY_RUN="${WATCH_DRY_RUN:-}"
NOW="${WATCH_NOW:-$(date +%s)}"
DAY=86400

# Only the named WATCH_* / PUBLIC_HOST lines are read from .env; nothing else is loaded or printed.
env_value() {
  local name=$1 default=$2 value=""
  if [ -n "${!name:-}" ]; then value=${!name}
  elif [ -f "$ENV_FILE" ]; then value=$(sed -n "s/^$name=//p" "$ENV_FILE" | tail -1 | tr -d '"'"'"' \r')
  fi
  printf '%s' "${value:-$default}"
}
FIVE_XX=$(env_value WATCH_5XX_THRESHOLD 5)
QUEUE_AGE=$(env_value WATCH_QUEUE_AGE_SECONDS 600)
DISK_PCT=$(env_value WATCH_DISK_PERCENT 85)
CERT_DAYS=$(env_value WATCH_CERT_DAYS 14)
HOST=$(env_value WATCH_HOST "$(env_value PUBLIC_HOST "")")
BACKUP_UNIT=$(env_value WATCH_BACKUP_UNIT mediease-backup.service)
CRITICAL_SERVICES=" db api web caddy "

declare -A found=()  # key -> "severity<TAB>message"
problem() { found[$1]="$2"$'\t'"$3"; }

check_containers() {
  local expected ps service state health line
  if ! expected=$($COMPOSE config --services 2>/dev/null); then
    problem docker critical "docker compose does not answer: the whole stack may be down"
    return
  fi
  ps=$($COMPOSE ps -a --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null) || ps=""
  for service in $expected; do
    [ "$service" = migrate ] && continue  # a one-off that exits after the migration
    line=$(awk -v s="$service" '$1 == s' <<<"$ps" | head -1)
    read -r _ state health <<<"$line"
    local severity=warning
    [[ "$CRITICAL_SERVICES" == *" $service "* ]] && severity=critical
    if [ -z "$line" ] || [ "$state" != running ]; then
      problem "container:$service" "$severity" "$service is not running (${state:-missing})"
    elif [ "$health" = unhealthy ]; then
      problem "container:$service" "$severity" "$service is running but unhealthy"
    fi
  done
}

check_errors() {
  local count
  count=$($COMPOSE logs --since 5m --no-log-prefix api 2>/dev/null \
    | grep -cE '"event": ?"(http\.server_error|app\.unexpected_error)"') || count=0
  if [ "$count" -ge "$FIVE_XX" ]; then
    problem errors warning "$count server errors in the API in the last 5 minutes (threshold $FIVE_XX)"
  fi
}

check_jobs() {
  local row dead stale oldest
  row=$($COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -qAt -F " " -c "select coalesce(sum(dead_24h),0), coalesce(sum(stale),0), coalesce(max(oldest_due_age_seconds),0) from v_job_health"' 2>/dev/null) || {
    problem jobs:query warning "could not read the job queue (v_job_health)"
    return
  }
  read -r dead stale oldest <<<"$row"
  [ "${dead:-0}" -gt 0 ] && problem jobs:dead warning "$dead dead jobs in the last 24 hours"
  [ "${stale:-0}" -gt 0 ] && problem jobs:stale warning "$stale running jobs stuck for over 5 minutes"
  [ "${oldest:-0}" -gt "$QUEUE_AGE" ] && problem jobs:queue warning \
    "the oldest due job has waited $((oldest / 60)) minutes (threshold $((QUEUE_AGE / 60)))"
  return 0
}

check_backup() {
  command -v systemctl >/dev/null || return 0
  systemctl cat "$BACKUP_UNIT" >/dev/null 2>&1 || return 0  # not installed (a local machine)
  local result ended
  result=$(systemctl show "$BACKUP_UNIT" -p Result --value 2>/dev/null)
  ended=$(systemctl show "$BACKUP_UNIT" -p ExecMainExitTimestamp --value --timestamp=unix 2>/dev/null)
  ended=${ended#@}
  if [ "$result" != success ]; then
    problem backup warning "the last backup failed ($result): journalctl -u $BACKUP_UNIT"
  elif [ -z "$ended" ] || [ $((NOW - ended)) -gt $((26 * 3600)) ]; then
    problem backup warning "no backup has finished in the last 26 hours"
  fi
}

check_disk() {
  local used
  used=$(df -P / | awk 'NR == 2 { sub("%", "", $5); print $5 }')
  [ "${used:-0}" -gt "$DISK_PCT" ] && problem disk warning "the disk is $used% full (threshold $DISK_PCT%)"
  return 0
}

check_certificate() {
  [ -n "$HOST" ] || return 0
  local end end_epoch days
  end=$(openssl s_client -connect "$HOST:443" -servername "$HOST" </dev/null 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null) || end=""
  end=${end#notAfter=}
  if [ -z "$end" ]; then
    problem certificate warning "could not read the certificate of $HOST"
    return
  fi
  end_epoch=$(date -d "$end" +%s 2>/dev/null) || return 0
  days=$(((end_epoch - NOW) / DAY))
  [ "$days" -lt "$CERT_DAYS" ] && problem certificate warning "the certificate of $HOST ends in $days days"
  return 0
}

check_containers
check_errors
check_jobs
check_backup
check_disk
check_certificate

# --- Decide what to send ---------------------------------------------------------------------
hour=$(TZ=Asia/Kolkata date -d "@$NOW" +%H)
hour=$((10#$hour))
in_hours=0; [ "$hour" -ge 8 ] && [ "$hour" -lt 22 ] && in_hours=1
sendable() { [ "$1" = critical ] || [ "$in_hours" = 1 ]; }

declare -A sent=() first=() sev=() msg=()  # the last state: key -> fields
if [ -f "$STATE" ]; then
  while IFS=$'\t' read -r key f s v m; do
    [ -n "$key" ] || continue
    first[$key]=$f; sent[$key]=$s; sev[$key]=$v; msg[$key]=$m
  done <"$STATE"
fi

new=() still=() cleared=() held=()
next=""
for key in $(printf '%s\n' "${!found[@]}" | sort); do
  IFS=$'\t' read -r severity message <<<"${found[$key]}"
  if ! sendable "$severity"; then
    held+=("$message")
    [ -n "${sent[$key]:-}" ] && next+="$key"$'\t'"${first[$key]}"$'\t'"${sent[$key]}"$'\t'"$severity"$'\t'"$message"$'\n'
    continue
  fi
  if [ -z "${sent[$key]:-}" ]; then
    new+=("[$severity] $message"); next+="$key"$'\t'"$NOW"$'\t'"$NOW"$'\t'"$severity"$'\t'"$message"$'\n'
  elif [ $((NOW - ${sent[$key]})) -ge $DAY ]; then
    still+=("[$severity] $message (since $(TZ=Asia/Kolkata date -d "@${first[$key]}" '+%d %b %H:%M IST'))")
    next+="$key"$'\t'"${first[$key]}"$'\t'"$NOW"$'\t'"$severity"$'\t'"$message"$'\n'
  else
    next+="$key"$'\t'"${first[$key]}"$'\t'"${sent[$key]}"$'\t'"$severity"$'\t'"$message"$'\n'
  fi
done
for key in $(printf '%s\n' "${!sent[@]}" | sort); do
  [ -n "${found[$key]:-}" ] && continue
  if sendable "${sev[$key]}"; then
    cleared+=("${msg[$key]}")
  else
    next+="$key"$'\t'"${first[$key]}"$'\t'"${sent[$key]}"$'\t'"${sev[$key]}"$'\t'"${msg[$key]}"$'\n'
  fi
done

# --- Report ----------------------------------------------------------------------------------
when=$(TZ=Asia/Kolkata date -d "@$NOW" '+%d %b %Y %H:%M IST')
if [ "${#found[@]}" -eq 0 ]; then echo "watch: all clear ($when)"; fi
for key in $(printf '%s\n' "${!found[@]}" | sort); do
  IFS=$'\t' read -r severity message <<<"${found[$key]}"
  echo "watch: [$severity] $message"
done
[ "${#held[@]}" -gt 0 ] && echo "watch: ${#held[@]} warning(s) held until 08:00 IST"

body=""
section() {
  local title=$1; shift
  [ "$#" -gt 0 ] || return 0
  body+="$title"$'\n'
  for line in "$@"; do body+="  - $line"$'\n'; done
  body+=$'\n'
}
section "New problems:" "${new[@]}"
section "Still failing (daily reminder):" "${still[@]}"
section "Resolved:" "${cleared[@]}"

if [ -z "$body" ]; then
  [ -n "$DRY_RUN" ] || { mkdir -p "$STATE_DIR"; printf '%s' "$next" >"$STATE"; }
  exit 0
fi

parts=()
[ "${#new[@]}" -gt 0 ] && parts+=("${#new[@]} new")
[ "${#still[@]}" -gt 0 ] && parts+=("${#still[@]} still failing")
[ "${#cleared[@]}" -gt 0 ] && parts+=("${#cleared[@]} resolved")
subject=$(IFS=,; echo "${parts[*]}" | sed 's/,/, /g')
body="Checked at $when."$'\n\n'"$body"

if [ -n "$DRY_RUN" ]; then
  printf 'watch: would email "%s":\n%s' "$subject" "$body"
  exit 0
fi

printf '%s' "$body" | $COMPOSE run --rm --no-deps -T api \
  python -m mediease_api.delivery.cli.ops_alert --subject "$subject"
case $? in
  0) mkdir -p "$STATE_DIR"; printf '%s' "$next" >"$STATE" ;;
  3) # OPS_ALERT_EMAIL is not set: the findings above are in this run's journal only. The state
     # is kept as it was, so the first run after the address is set emails them.
     echo "watch: OPS_ALERT_EMAIL is not set; nothing emailed (RUNBOOK §41)" ;;
  *) echo "watch: the alert email was not sent; the next run tries again" >&2; exit 1 ;;
esac
