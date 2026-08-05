#!/usr/bin/env bash
set -uo pipefail

# ---------------------------------------------------------------------------
# OMA Browser API — access-control smoke test (non-interactive)
#
# Verifies the nginx tiered rate-limit routing introduced with oauth2-proxy:
#   - website AJAX (sec-fetch-site: same-origin + sec-fetch-mode: cors) passes
#     without a token and is never rate-limited
#   - direct browser navigation to an /api/ URL (sec-fetch-mode: navigate,
#     even if same-origin — this is the pattern a distributed crawler used to
#     exploit) is NOT exempted, and is served at the anonymous rate instead
#   - external clients without a token are served (not blocked) at the
#     anonymous rate, instead of the old hard 401/sign-in-redirect
#   - the public auth endpoints and /oma/ pages stay open
#
# Usage:
#   ./test_api_access.sh [API_PATH]
#
# Env vars:
#   OMA_BASE_URL        base URL to test           (default: http://localhost)
#   OMA_ACCESS_TOKEN    a valid Bearer token       (optional; enables the
#                       authenticated-path test without a browser login)
#   OMA_TEST_RATE_LIMIT set to 1 to also fire a burst of anonymous requests
#                       and confirm a 429 is returned (default: skipped —
#                       this deliberately burns through the anon-tier quota
#                       for the caller's own IP)
#
# Exits non-zero if any check fails, so it can be wired into CI.
#
# NOTE: the Fetch Metadata checks below prove the *routing*, not a security
# boundary. sec-fetch-site/sec-fetch-mode are spoofable request headers, so
# this is a UX/cost-shaping gate for public scientific data, not protection
# of the API contents.
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
echo "== Free tier: real website AJAX =="

# 1. Website AJAX: same-origin + a fetch/XHR mode passes freely without a token.
code=$(status -H "sec-fetch-site: same-origin" -H "sec-fetch-mode: cors" "${OMA_BASE_URL}${API_PATH}")
check "same-origin + cors (real AJAX) passes (no token)" "200" "$code"

echo ""
echo "== Anonymous tier: served, not blocked =="

# 2. The crawler pattern found in production: same-origin navigation to an
#    /api/ URL is NOT exempted just because sec-fetch-site says same-origin —
#    sec-fetch-mode: navigate means it's a page load, not real AJAX. It's
#    still served (anonymous tier), just no longer free.
code=$(status -H "sec-fetch-site: same-origin" -H "sec-fetch-mode: navigate" "${OMA_BASE_URL}${API_PATH}")
check "same-origin + navigate (crawler pattern) is served, not exempted" "200" "$code"

# 3. External client, no token, no Fetch Metadata headers at all -> served
#    (anonymous tier), not the old hard 401/redirect.
code=$(status "${OMA_BASE_URL}${API_PATH}")
check "external client no token -> served (anonymous tier)" "200" "$code"

# 4. Optional: burn through the anonymous quota and confirm a 429 shows up,
#    with the expected JSON body. Off by default since it deliberately
#    exhausts the caller's own anon-tier rate limit.
if [ "${OMA_TEST_RATE_LIMIT:-0}" = "1" ]; then
  echo ""
  echo "== Rate-limit burst test (OMA_TEST_RATE_LIMIT=1) =="
  tripped=0
  for i in $(seq 1 30); do
    body=$("${CURL[@]}" -o /tmp/oma_burst_body -w "%{http_code}" -H "sec-fetch-site: same-origin" -H "sec-fetch-mode: navigate" "${OMA_BASE_URL}${API_PATH}")
    if [ "$body" = "429" ]; then
      tripped=1
      break
    fi
  done
  if [ "$tripped" -eq 1 ]; then
    printf "  PASS  %-48s got 429 after %s requests\n" "anonymous burst trips rate limit" "$i"
    pass=$((pass + 1))
    if grep -q '"detail"' /tmp/oma_burst_body 2>/dev/null; then
      echo "        body: $(cat /tmp/oma_burst_body)"
    else
      echo "  FAIL  429 body is not the expected JSON {\"detail\":...}"
      fail=$((fail + 1))
    fi
  else
    echo "  FAIL  30 rapid anonymous requests never hit a 429 — is the anon rate limit configured?"
    fail=$((fail + 1))
  fi

  # Confirm real website AJAX is still unaffected even right after tripping
  # the anonymous limit above.
  code=$(status -H "sec-fetch-site: same-origin" -H "sec-fetch-mode: cors" "${OMA_BASE_URL}${API_PATH}")
  check "same-origin + cors still unaffected after anon burst" "200" "$code"
fi

echo ""
echo "== Endpoints that must stay public =="

# 5. Device-flow endpoint is public (exact-match location, no auth_request).
code=$(status -X POST "${OMA_BASE_URL}/api/auth/device")
check "POST /api/auth/device is public" "200" "$code"

# 6. /oma/ site pages are not gated by auth_request.
code=$(status "${OMA_BASE_URL}/oma/home/")
case "$code" in
  401|403) echo "  FAIL  /oma/home/ is gated (got $code)"; fail=$((fail + 1)) ;;
  *) printf "  PASS  %-48s got %s\n" "/oma/home/ reachable (not gated)" "$code"; pass=$((pass + 1)) ;;
esac

# 7. Authenticated path (only if a token is supplied).
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
