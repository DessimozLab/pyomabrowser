# API Authentication

The OMA Browser REST API (`/api/`) is protected by [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) integrated with Keycloak. Public paths (`/oma/`, `/static/`, `/media/`) require no authentication.

## Architecture

```
internet → nginx:80 (public) → web:8000
                │
                └─ auth_request → oauth2-proxy:4180 (internal)
```

nginx is the public entry point. It routes all traffic and uses the `auth_request` directive to validate `/api/` calls. oauth2-proxy runs in forward-auth mode (it does not proxy traffic anymore). It only validates session cookies and Bearer tokens through its `/oauth2/auth` endpoint, returning 200 or 401 to nginx's `auth_request` subrequests. oauth2-proxy is exposed inside the Docker network only (not published on the host).

An internal nginx location, `/_auth_check`, inspects the `sec-fetch-site` request header before deciding whether to call oauth2-proxy:

- `sec-fetch-site: same-origin` (browser AJAX from the website) returns 200 directly, so it passes freely without contacting oauth2-proxy.
- Any other value proxies the subrequest to `oauth2-proxy:4180/oauth2/auth`, which validates the session cookie or Bearer token.

On a 401 from oauth2-proxy, nginx looks at `sec-fetch-mode`. If it is `navigate` (a browser navigating directly to the URL), nginx issues a 302 redirect to `/oauth2/sign_in`. Otherwise it returns a 401 with the JSON body `{"detail":"Authentication credentials were not provided."}`.

### Why `sec-fetch-site` is a reliable signal

`sec-fetch-site: same-origin` is a W3C Fetch Metadata header that modern browsers set automatically on AJAX requests made from the same origin. Standard HTTP clients (curl, Python requests, wget) do not send it, and JavaScript cannot override it because browsers enforce it. This distinguishes "website AJAX" from "external API call" reliably. Headless browsers (such as Playwright) can fake it, an accepted tradeoff for public scientific data.

## Access patterns

### Website (browser AJAX)

Requests made by the OMA Browser website's own JavaScript (same origin) carry `sec-fetch-site: same-origin`. The `/_auth_check` location returns 200 for these without contacting oauth2-proxy, so the website's API calls work without any login. This keeps the interactive site fully functional for anonymous visitors.

### Browser (direct navigation)

Navigate to any `/api/` URL directly in the address bar. Because there is no valid session, oauth2-proxy returns 401 and nginx detects `sec-fetch-mode: navigate`, redirecting you to `/oauth2/sign_in`. You log in via Keycloak (supports OTP and passkeys) and are returned to the original URL automatically with an encrypted session cookie.

### Script / programmatic access

Use `test_api_auth.sh`. It authenticates via the device flow: a URL is printed, you log in via browser (supports OTP and passkeys), and the script receives the token automatically.

```bash
./test_api_auth.sh /api/schema/
./test_api_auth.sh /api/protein/HUMAN5/
```

No Keycloak credentials or secrets are required in the script. Authentication happens entirely in your browser.

The script caches the refresh token in `~/.oma_token` (mode 600). On subsequent runs it silently refreshes the access token without opening a browser. Browser login is only required again when the SSO session expires (determined by your Keycloak realm's SSO Session Max and SSO Session Idle settings).

To force a new login, delete the cache file:

```bash
rm ~/.oma_token
```

Programmatic clients send no `sec-fetch-site` header, so their requests are validated by oauth2-proxy. A missing or invalid token returns a 401 JSON response; a valid Bearer token is allowed through to Django.

## Testing

Two scripts cover the access-control behavior.

`test_api_access.sh` is a non-interactive smoke test for the nginx routing. It requires no login and checks each access path by sending the headers a browser would set:

```bash
./test_api_access.sh
OMA_BASE_URL=https://yourdomain.com ./test_api_access.sh
```

It verifies that same-origin AJAX passes without a token (200), that an external client with no token gets a JSON 401, that browser navigation is redirected to `/oauth2/sign_in` (302), and that `POST /api/auth/device` and `/oma/` pages stay public. It exits non-zero if any check fails, so it can be wired into CI. To also test the authenticated path, pass a token (obtain one with `test_api_auth.sh`):

```bash
OMA_ACCESS_TOKEN=<bearer-token> ./test_api_access.sh
```

`test_api_auth.sh` (see [Script / programmatic access](#script--programmatic-access)) is the interactive end-to-end test of the Bearer-token path through the full device flow.

A few things the smoke test cannot cover and which need a manual check:

- **Real website AJAX.** The smoke test only simulates `sec-fetch-site: same-origin` with curl. Confirm the genuine header works by opening the site in a browser while logged out and verifying that pages whose content loads via API calls still render.
- **Django-level 401s.** The `/api/` location maps any 401 to the sign-in redirect or JSON response. If Django itself returns a 401 for an authenticated-but-unauthorized request, nginx rewrites it. Check such an endpoint with a valid token and confirm the response is the one you expect.

This is a UX gate, not a security boundary. `sec-fetch-site` is a request header that any client can set (`curl -H "sec-fetch-site: same-origin"` bypasses the check entirely), so the API contents are effectively public. That is acceptable for public scientific data but should not be relied on to protect anything sensitive.

## Token lifespan

The refresh token lifetime is controlled by the Keycloak realm's SSO session settings (Realm Settings → Sessions). The Edu-ID realm defaults are:

| Setting | Default | Effect |
|---|---|---|
| SSO Session Idle | 30 minutes | Session expires if unused for this long |
| SSO Session Max | 10 hours | Absolute session lifetime regardless of activity |

Browser login will be required again once either limit is hit. Short access tokens (Realm Settings → Tokens → Access Token Lifespan, default 5 minutes) limit exposure if a token is intercepted; the cached refresh token is used to obtain new access tokens silently within the session window.

## Keycloak setup

### 1. Find the OIDC issuer URL

1. Log into the Keycloak admin console
2. Select your realm from the top-left dropdown
3. Left sidebar → **Realm settings** → **General** tab
4. Click the **OpenID Endpoint Configuration** link (opens a JSON document)
5. Copy the value of the `"issuer"` field, e.g. `https://sso.example.com/realms/myrealm`
6. Set `OAUTH2_PROXY_OIDC_ISSUER_URL=https://sso.example.com/realms/myrealm`

### 2. Create the client

1. Left sidebar → **Clients** → **Create client**
2. **General settings**:
   - Client type: `OpenID Connect`
   - Client ID: choose a name, e.g. `omabrowser` → set `OAUTH2_PROXY_CLIENT_ID=omabrowser`
   - Click **Next**
3. **Capability config**:
   - Client authentication: **ON** (enables client secret)
   - Authentication flow: keep **Standard flow** checked (browser login)
   - Also check **OAuth 2.0 Device Authorization Grant** (script login via device flow)
   - Click **Next**
4. **Login settings**:
   - Valid redirect URIs: `https://yourdomain.com/oauth2/callback`
     (for local testing: `http://localhost/oauth2/callback`)
   - Set `OAUTH2_PROXY_REDIRECT_URL=https://yourdomain.com/oauth2/callback`
   - Click **Save**

### 3. Get the client secret

1. Open the newly created client → **Credentials** tab
2. Copy the **Client secret** value
3. Set `OAUTH2_PROXY_CLIENT_SECRET=<copied value>`

### 4. Add the audience mapper

This step is required. Without it, Keycloak issues tokens with `aud: account` and oauth2-proxy rejects them.

1. Open the client → **Client Scopes** tab
2. Click on `<your-client-id>-dedicated` (e.g. `omabrowser-dedicated`), it is a hyperlink
3. **Mappers** tab → **Add mapper** → **By configuration**
4. Choose **Audience** from the list
5. Fill in:
   - Name: anything, e.g. `add-client-audience`
   - **Included Client Audience**: select your client ID from the dropdown (e.g. `omabrowser`)
   - Add to access token: **ON**
6. Click **Save**

After this, tokens issued for this client will include `"aud": ["account", "omabrowser"]` and oauth2-proxy will accept them.

### 5. Generate the cookie secret

This is not from Keycloak. Run once on your server:

```bash
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Set `OAUTH2_PROXY_COOKIE_SECRET=<output>`.

### 6. Resulting `env` file block

```
OAUTH2_PROXY_OIDC_ISSUER_URL=https://sso.example.com/realms/myrealm
OAUTH2_PROXY_CLIENT_ID=omabrowser
OAUTH2_PROXY_CLIENT_SECRET=<from Credentials tab>
OAUTH2_PROXY_COOKIE_SECRET=<from python3 command above>
OAUTH2_PROXY_REDIRECT_URL=https://yourdomain.com/oauth2/callback
OAUTH2_PROXY_COOKIE_SECURE=true
```

## How the token proxy works

Two nginx endpoints inject the client secret server-side so it never needs to be distributed to users:

- `POST /api/auth/device`: starts device flow, returns `device_code` and `verification_uri`
- `POST /api/auth/token`: exchanges `device_code` for a bearer token, or refreshes an existing session using a `refresh_token`

These are exact-match nginx locations that proxy directly to Keycloak and take precedence over the general `/api/` location. They are public (no auth required). All other `/api/` paths are protected via `auth_request /_auth_check`, which either passes the request (website AJAX or valid session/token) or rejects it (redirect to sign-in for browser navigation, 401 JSON for programmatic clients).

## Configuration reference (`env` file)

| Variable | Description |
|---|---|
| `OAUTH2_PROXY_OIDC_ISSUER_URL` | Keycloak realm URL (see step 1 above) |
| `OAUTH2_PROXY_CLIENT_ID` | Client ID from Keycloak (see step 2) |
| `OAUTH2_PROXY_CLIENT_SECRET` | Client secret from Keycloak Credentials tab (see step 3) |
| `OAUTH2_PROXY_COOKIE_SECRET` | Random 32-byte base64 string (see step 5) |
| `OAUTH2_PROXY_REDIRECT_URL` | `https://<yourdomain>/oauth2/callback`, registered in Keycloak valid redirect URIs |
| `OAUTH2_PROXY_COOKIE_SECURE` | Set to `true` when serving over HTTPS |
| `OAUTH2_PROXY_OIDC_AUDIENCES` | Accepted token audiences. Set to `account` (Keycloak default audience). Bearer token validation uses the client ID from the JWT directly and is not affected by this setting. |
