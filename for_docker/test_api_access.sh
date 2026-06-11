#!/usr/bin/env bash
set -uo pipefail

# ---------------------------------------------------------------------------
# OMA Browser API — access-control smoke test (non-interactive)
#
# Verifies the nginx forward-auth routing introduced with oauth2-proxy:
#   - website AJAX (sec-fetch-site: same-origin) passes without a token
#   - external clients without a token get a JSON 401
#   - browser navigation (sec-fetch-mode: navigate) is redirected to sign-in
#   - the public auth endpoints and /oma/ pages stay open
#
# Usage:
#   ./test_api_access.sh [API_PATH]
#
# Env vars:
#   OMA_BASE_URL        base URL to test         (default: http://localhost)
#   OMA_ACCESS_TOKEN    a valid Bearer token     (optional; enables the
#                       authenticated-path test without a browser login)
#
# Exits non-zero if any check fails, so it can be wired into CI.
#
# NOTE: the same-origin check below proves the *routing*, not a security
# boundary. sec-fetch-site is a spoofable request header, so this is a UX
# gate for public scientific data, not protection of the API contents.
# ---------------------------------------------------------------------------

OMA_BASE_URL="${OMA_BASE_URL:-http://localhost}"
API_PATH="${1:-/api/schema/}"
CURL=(curl -s --max-time 15)

pass=0
fail=0

# check NAME EXPECTED ACTUAL [extra-detail]
check() {
  local name="$1" expected="$2" actual="$3" extra="${4:-}"
  if [ "$actual" = "$expected" ]; then
    printf "  PASS  %-48s got %s\n" "$name" "$actual"
    pass=$((pass + 1))
  else
    printf "  FAIL  %-48s expected %s, got %s %s\n" "$name" "$expected" "$actual" "$extra"
    fail=$((fail + 1))
  fi
}

# code for a request; pass extra curl args
status() {
  "${CURL[@]}" -o /dev/null -w "%{http_code}" "$@"
}

echo "Testing ${OMA_BASE_URL} (API path: ${API_PATH})"
echo ""
echo "== Public access (no token) =="

# 1. Website AJAX: same-origin passes freely without a token.
code=$(status -H "sec-fetch-site: same-origin" "${OMA_BASE_URL}${API_PATH}")
check "same-origin AJAX passes (no token)" "200" "$code"

# 2. External client, no token, no header -> JSON 401.
body=$("${CURL[@]}" -o /tmp/oma_access_body -w "%{http_code}" "${OMA_BASE_URL}${API_PATH}")
check "external client no token -> 401" "401" "$body"
if grep -q '"detail"' /tmp/oma_access_body 2>/dev/null; then
  echo "        body: $(cat /tmp/oma_access_body)"
else
  echo "  FAIL  401 body is not the expected JSON {\"detail\":...}"
  fail=$((fail + 1))
fi

# 3. Browser direct navigation -> 302 redirect to the sign-in page.
headers=$("${CURL[@]}" -D - -o /dev/null -H "sec-fetch-mode: navigate" "${OMA_BASE_URL}${API_PATH}")
code=$(printf '%s\n' "$headers" | grep -iE '^HTTP/' | tail -1 | awk '{print $2}')
location=$(printf '%s\n' "$headers" | grep -i '^location:' | tr -d '\r' | awk '{print $2}')
check "browser navigation -> 302" "302" "$code"
case "$location" in
  */oauth2/sign_in*) echo "        location: $location" ;;
  *) echo "  FAIL  redirect target is not /oauth2/sign_in (got: ${location:-none})"; fail=$((fail + 1)) ;;
esac

echo ""
echo "== Endpoints that must stay public =="

# 4. Device-flow endpoint is public (exact-match location, no auth_request).
code=$(status -X POST "${OMA_BASE_URL}/api/auth/device")
check "POST /api/auth/device is public" "200" "$code"

# 5. /oma/ site pages are not gated by auth_request.
code=$(status "${OMA_BASE_URL}/oma/home/")
case "$code" in
  401|403) echo "  FAIL  /oma/home/ is gated (got $code)"; fail=$((fail + 1)) ;;
  *) printf "  PASS  %-48s got %s\n" "/oma/home/ reachable (not gated)" "$code"; pass=$((pass + 1)) ;;
esac

# 6. Authenticated path (only if a token is supplied).
if [ -n "${OMA_ACCESS_TOKEN:-}" ]; then
  echo ""
  echo "== Authenticated access =="
  code=$(status -H "Authorization: Bearer ${OMA_ACCESS_TOKEN}" "${OMA_BASE_URL}${API_PATH}")
  check "valid Bearer token -> 200" "200" "$code"
else
  echo ""
  echo "  SKIP  authenticated-path test (set OMA_ACCESS_TOKEN to enable;"
  echo "        obtain one with ./test_api_auth.sh)"
fi

echo ""
echo "Result: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
