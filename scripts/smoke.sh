#!/usr/bin/env bash
# End-to-end smoke test of the running local stack (`make up` first).
# Used by `make smoke` locally and by the CI smoke job, so "a fresh clone works"
# is checked the same way everywhere. Exits non-zero on the first failure.
#
# Usage: scripts/smoke.sh            (ports from API_PORT / WEB_PORT, default 8000 / 3000)
set -euo pipefail

API="http://localhost:${API_PORT:-8000}"
WEB="http://localhost:${WEB_PORT:-3000}"
COMPOSE="${COMPOSE:-docker compose}"

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1" >&2; exit 1; }

# Body of a URL, failing on non-2xx or no answer within 15 s.
get() { curl -fsS -m 15 "$1"; }
# Response headers of a URL. Output is captured, never piped straight into
# `grep -q`: grep exits on the first match, curl then dies of SIGPIPE, and
# pipefail turns a passing check into a random failure.
headers() { curl -fsS -m 15 -D - -o /dev/null "$1"; }
# Visible text of an HTML page (tags stripped).
text() { get "$1" | sed 's/<[^>]*>//g'; }

echo "Services"
state() { $COMPOSE ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}}' | awk -v s="$1" '$1 == s'; }
for svc in db api web; do
  [[ "$(state "$svc")" == "$svc running healthy"* ]] && pass "$svc running and healthy" || fail "$svc not healthy: $(state "$svc")"
done
[[ "$(state migrate)" == "migrate exited "*" 0" ]] && pass "migrate exited 0" || fail "migrate: $(state migrate)"

echo "API"
[[ "$(get "$API/health")" == '{"status":"ok"}' ]] && pass "/health" || fail "/health"
[[ "$(get "$API/ready")" == *'"database":"ok"'* ]] && pass "/ready (database ok)" || fail "/ready"

echo "Web"
[[ "$(get "$WEB/livez")" == '{"status":"ok"}' ]] && pass "/livez" || fail "/livez"
proxied=$(headers "$WEB/health")
grep -qi '^x-request-id:' <<<"$proxied" \
  && pass "/health proxied to the API (X-Request-ID returned)" || fail "/health proxy"
page=$(text "$WEB/status")
grep -q 'API: healthy · DB: ready · Ref: ' <<<"$page" \
  && pass "/status shows API healthy and DB ready" || fail "/status"
page_headers=$(headers "$WEB/status")
grep -qi "^content-security-policy:.*'nonce-" <<<"$page_headers" \
  && pass "/status sends a nonce CSP" || fail "CSP header"
signin=$(text "$WEB/sign-in")
grep -q 'Sign in to MediEase' <<<"$signin" && grep -q 'Email or phone number' <<<"$signin" \
  && pass "/sign-in renders the sign-in form" || fail "/sign-in form"
signin_headers=$(headers "$WEB/sign-in")
grep -qi "^content-security-policy:.*'nonce-" <<<"$signin_headers" \
  && pass "/sign-in sends a nonce CSP" || fail "/sign-in CSP header"
# Without a session cookie a clinic page redirects to sign in (curl -f would fail on a 307).
redirect=$(curl -sS -m 15 -D - -o /dev/null "$WEB/queue")
grep -qE '^HTTP/[0-9.]+ 307' <<<"$redirect" && grep -qi '^location: .*/sign-in?next=%2Fqueue' <<<"$redirect" \
  && pass "/queue without a session redirects to /sign-in?next=/queue" || fail "/queue redirect: $redirect"
grep -qi "^content-security-policy:.*'nonce-" <<<"$redirect" \
  && pass "the redirect also sends a CSP" || fail "redirect CSP header"
# The patient screens (M2-P5) are clinic pages too: no session, no patient page.
redirect=$(curl -sS -m 15 -D - -o /dev/null "$WEB/patients?q=rao")
grep -qE '^HTTP/[0-9.]+ 307' <<<"$redirect" && grep -qi '^location: .*/sign-in?next=%2Fpatients' <<<"$redirect" \
  && pass "/patients without a session redirects to /sign-in" || fail "/patients redirect: $redirect"
# The patient API refuses anonymous callers through the web origin (FR-AUTH-03).
status=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$WEB/api/v1/patients?q=rao")
[ "$status" = "401" ] && pass "/api/v1/patients without a session is 401" || fail "/api/v1/patients anonymous: $status"

echo "Least privilege"
for svc in api web; do
  uid=$($COMPOSE exec -T "$svc" id -u)
  [[ "$uid" != "0" ]] && pass "$svc runs as uid $uid (not root)" || fail "$svc runs as root"
  if $COMPOSE exec -T "$svc" sh -c 'touch /smoke-write-test' 2>/dev/null; then
    fail "$svc root filesystem is writable"
  fi
  pass "$svc root filesystem is read-only"
  caps=$($COMPOSE exec -T "$svc" sh -c "awk '/^CapEff:/ {print \$2}' /proc/self/status")
  [[ "$caps" =~ ^0+$ ]] && pass "$svc has no capabilities" || fail "$svc capabilities: $caps"
done

echo "Smoke test passed."
