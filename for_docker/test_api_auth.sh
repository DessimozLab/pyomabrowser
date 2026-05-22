#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# OMA Browser API — authenticated access
# Usage: ./test_api_auth.sh [API_PATH]
# Example: ./test_api_auth.sh /api/schema/
#
# Authenticates via device flow (browser-based, supports OTP and passkeys).
# Caches the refresh token in ~/.oma_token so browser login is only needed
# once per SSO session (idle: 30 min, max: 10 h on Edu-ID). No Keycloak credentials or secrets required.
# ---------------------------------------------------------------------------

# -- Admin: set this before distributing the script --
OMA_BASE_URL="http://localhost"
# ----------------------------------------------------

TOKEN_CACHE="${HOME}/.oma_token"
API_PATH="${1:-/api/schema/}"

ACCESS_TOKEN=""

# Try cached refresh token first
if [ -f "$TOKEN_CACHE" ]; then
  CACHED_REFRESH=$(cat "$TOKEN_CACHE")
  REFRESH_RESPONSE=$(curl -s -X POST "${OMA_BASE_URL}/api/auth/token" \
    --data-urlencode "grant_type=refresh_token" \
    --data-urlencode "refresh_token=${CACHED_REFRESH}")

  REFRESH_ERROR=$(echo "$REFRESH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null || echo "parse_error")

  if [ -z "$REFRESH_ERROR" ]; then
    ACCESS_TOKEN=$(echo "$REFRESH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
    NEW_REFRESH=$(echo "$REFRESH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null)
    if [ -n "$NEW_REFRESH" ]; then
      echo "$NEW_REFRESH" > "$TOKEN_CACHE"
      chmod 600 "$TOKEN_CACHE"
    fi
  else
    echo "Cached session expired, starting new login..."
    rm -f "$TOKEN_CACHE"
  fi
fi

# Full device flow if no valid cached token
if [ -z "$ACCESS_TOKEN" ]; then
  echo "Starting authentication..."
  DEVICE_RESPONSE=$(curl -s -X POST "${OMA_BASE_URL}/api/auth/device")

  DEVICE_CODE=$(echo "$DEVICE_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('device_code',''))" 2>/dev/null)
  VERIFY_URL=$(echo "$DEVICE_RESPONSE"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('verification_uri_complete', d.get('verification_uri','')))" 2>/dev/null)
  INTERVAL=$(echo "$DEVICE_RESPONSE"    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('interval', 5))" 2>/dev/null)

  if [ -z "$DEVICE_CODE" ]; then
    echo "ERROR: Failed to start device flow. Response:"
    echo "$DEVICE_RESPONSE"
    exit 1
  fi

  echo ""
  echo "Open this URL in your browser to log in:"
  echo ""
  echo "  ${VERIFY_URL}"
  echo ""
  echo "Waiting for you to complete login..."

  while true; do
    sleep "${INTERVAL}"
    TOKEN_RESPONSE=$(curl -s -X POST "${OMA_BASE_URL}/api/auth/token" \
      --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
      --data-urlencode "device_code=${DEVICE_CODE}")

    ERROR=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null)

    if [ "$ERROR" = "authorization_pending" ]; then
      continue
    elif [ "$ERROR" = "slow_down" ]; then
      INTERVAL=$((INTERVAL + 5))
      continue
    elif [ -n "$ERROR" ]; then
      echo "Authentication failed: ${ERROR}"
      exit 1
    fi

    ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
    REFRESH_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null)
    break
  done

  if [ -z "$ACCESS_TOKEN" ]; then
    echo "ERROR: No access_token in response."
    exit 1
  fi

  if [ -n "$REFRESH_TOKEN" ]; then
    echo "$REFRESH_TOKEN" > "$TOKEN_CACHE"
    chmod 600 "$TOKEN_CACHE"
    echo "Session cached. Future runs will reuse it until the SSO session expires (idle: 30 min, max: 10 h)."
  fi

  echo "Authenticated successfully."
fi

echo ""
echo "Calling: ${OMA_BASE_URL}${API_PATH}"

HTTP_CODE=$(curl -s -o /tmp/oma_response.json -w "%{http_code}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "${OMA_BASE_URL}${API_PATH}")

echo "HTTP status: ${HTTP_CODE}"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
  cat /tmp/oma_response.json
elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ]; then
  echo "Access denied."
  cat /tmp/oma_response.json
else
  echo "Unexpected response:"
  cat /tmp/oma_response.json
fi
