#!/usr/bin/env bash
# Smoke test of a deployed site from the outside (M9-P1 C5; RUNBOOK §38). Run from any machine:
#
#   make smoke-live URL=https://mediease.duckdns.org [SLUG=kesar-bagh-family-clinic]
#
# Checks HTTPS and the certificate, the HTTP redirect, health through the web origin, security
# headers, sign-in protection, the upload size limit, the public clinic page (with SLUG), and that
# nothing but 80 and 443 answers on the host. Signs in as nobody and writes nothing.
set -euo pipefail

URL="${1:-${URL:-}}"
SLUG="${2:-${SLUG:-}}"
[ -n "$URL" ] || { echo "usage: scripts/smoke-live.sh https://host [clinic-slug]" >&2; exit 2; }
URL="${URL%/}"
HOST="${URL#https://}"
HOST="${HOST%%/*}"
[[ "$URL" == https://* ]] || { echo "smoke-live: the URL must start with https://" >&2; exit 2; }

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1" >&2; exit 1; }
# curl verifies the certificate (no -k): a bad or expired certificate fails here.
get() { curl -fsS -m 20 "$1"; }
headers() { curl -fsS -m 20 -D - -o /dev/null "$1"; }
status_of() { curl -sS -m 30 -o /dev/null -w '%{http_code}' "$@"; }

echo "HTTPS"
get "$URL/livez" > /dev/null && pass "certificate valid for $HOST" || fail "HTTPS or certificate"
expiry=$(echo | openssl s_client -servername "$HOST" -connect "$HOST:443" 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || true)
[ -n "$expiry" ] && pass "certificate valid until $expiry" || fail "could not read the certificate"
redirect=$(curl -sS -m 20 -D - -o /dev/null "http://$HOST/queue")
grep -qE '^HTTP/[0-9.]+ 30[18]' <<<"$redirect" && grep -qi "^location: https://$HOST/queue" <<<"$redirect" \
  && pass "http:// redirects to https://" || fail "HTTP redirect: $redirect"

echo "Health"
[[ "$(get "$URL/livez")" == '{"status":"ok"}' ]] && pass "/livez" || fail "/livez"
[[ "$(get "$URL/health")" == '{"status":"ok"}' ]] && pass "/health (API through the web)" || fail "/health"
[[ "$(get "$URL/ready")" == *'"database":"ok"'* ]] && pass "/ready (database ok)" || fail "/ready"

echo "Headers"
page=$(headers "$URL/sign-in")
grep -qi '^strict-transport-security: max-age=' <<<"$page" && pass "HSTS" || fail "no HSTS header"
grep -qi "^content-security-policy:.*'nonce-" <<<"$page" && pass "nonce CSP" || fail "no CSP"
if grep -qi '^server:' <<<"$page"; then fail "a Server header is sent"; fi
pass "no Server header"

echo "Access"
redirect=$(curl -sS -m 20 -D - -o /dev/null "$URL/queue")
grep -qE '^HTTP/[0-9.]+ 307' <<<"$redirect" && grep -qi '^location: .*/sign-in?next=%2Fqueue' <<<"$redirect" \
  && pass "/queue without a session redirects to sign-in" || fail "/queue redirect"
[ "$(status_of "$URL/api/v1/patients?q=a")" = "401" ] && pass "/api/v1/patients anonymous is 401" \
  || fail "/api/v1/patients anonymous"
status=$(head -c 11000000 /dev/zero | curl -sS -m 60 -o /dev/null -w '%{http_code}' -X POST \
  -H 'Content-Type: multipart/form-data; boundary=x' --data-binary @- "$URL/api/v1/portal/prescription-uploads")
[ "$status" = "413" ] && pass "an 11 MB upload is 413" || fail "oversized upload: $status"

if [ -n "$SLUG" ]; then
  echo "Public clinic page"
  [ "$(status_of "$URL/c/$SLUG")" = "200" ] && pass "/c/$SLUG is public" || fail "/c/$SLUG"
fi

echo "Closed ports on $HOST"
for port in 22 3000 3310 5432 8000; do
  if timeout 4 bash -c "</dev/tcp/$HOST/$port" 2>/dev/null; then
    # 22 is open only to Google's IAP range; from anywhere else it must not answer.
    fail "port $port answers from here"
  fi
  pass "port $port does not answer"
done

echo "Live smoke test passed."
