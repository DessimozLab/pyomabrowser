# API Authentication

The OMA Browser REST API (`/api/`) sits behind [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) integrated with Keycloak, and behind a set of nginx rate limits that split callers into tiers. Public paths (`/oma/`, `/static/`, `/media/`) require no authentication and are not rate-limited by this mechanism.

## Architecture

```
internet → nginx:80 (public) → web:8000
                │
                └─ auth_request → oauth2-proxy:4180 (internal)
```

nginx is the public entry point. It routes all traffic and uses the `auth_request` directive to validate `/api/` calls. oauth2-proxy runs in forward-auth mode (it does not proxy traffic anymore). It only validates session cookies and Bearer tokens through its `/oauth2/auth` endpoint, returning 200 or 401 to nginx's `auth_request` subrequests. oauth2-proxy is exposed inside the Docker network only (not published on the host).

An internal nginx location, `/_auth_check`, inspects Fetch Metadata request headers before deciding whether to call oauth2-proxy:

- `sec-fetch-site: same-origin` **and** `sec-fetch-mode: cors` or `same-origin` (a real `fetch()`/XHR call from the website's own JavaScript) returns 200 directly, so it passes freely without contacting oauth2-proxy.
- Anything else proxies the subrequest to `oauth2-proxy:4180/oauth2/auth`, which validates the session cookie or Bearer token.

Unlike before, oauth2-proxy returning 401 no longer blocks the request outright — it's served anyway, at the strict anonymous rate limit (see "Rate limits" below). Authentication now determines *how generous your limit is*, not *whether you're let in at all*.

### Why both `sec-fetch-site` and `sec-fetch-mode` are checked

`sec-fetch-site`/`sec-fetch-mode` are W3C Fetch Metadata headers that modern browsers set automatically and that JavaScript cannot override, because browsers enforce them. Standard HTTP clients (curl, Python requests, wget) do not send them at all.

Checking only `sec-fetch-site: same-origin` turned out to be too broad: analysis of production traffic showed a large, distributed crawler (real or headless browser engines, ~26k distinct source IPs) directly navigating to `/api/...` URLs — most likely following the DRF browsable-API's own hyperlinks between related resources. Because it genuinely navigates from an omabrowser.org page to an omabrowser.org URL, `sec-fetch-site: same-origin` is not spoofed — it's just not what the check is meant to exempt. The tell is `sec-fetch-mode`: a real page navigation (clicking a link, typing a URL) always sends `sec-fetch-mode: navigate`, while `fetch()`/XHR calls (what the website's own AJAX actually uses) send `cors` or `same-origin`. Requiring both headers together reclassified that traffic out of the free tier and into the rate-limited ones. A moderately sophisticated client can still fake both headers deliberately — this remains a UX/cost-shaping gate, not a security boundary (see below).

## Access patterns

### Website (browser AJAX)

Requests made by the OMA Browser website's own JavaScript (same origin, `fetch()`/XHR) carry `sec-fetch-site: same-origin` and `sec-fetch-mode: cors`/`same-origin`. The `/_auth_check` location returns 200 for these without contacting oauth2-proxy, so the website's API calls work without any login and are not rate-limited — even if the visitor happens to also be logged in. This keeps the interactive site fully functional for anonymous visitors.

### Browser (direct navigation) and other anonymous callers

Navigate to any `/api/` URL directly in the address bar, or call it with curl/a script/a crawler without a valid session or token. There is no forced login and no redirect to sign-in anymore — the request is served directly, capped at a strict rate (see "Rate limits"). Logging in via `/oauth2/sign_in` (Keycloak, supports OTP and passkeys) raises that cap substantially, since an authenticated identity is harder to mint at scale than a new source IP.

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

Programmatic clients send no `sec-fetch-site` header, so their requests are validated by oauth2-proxy. A missing or invalid token gets the anonymous rate limit; a valid Bearer token gets the higher authenticated rate limit, both proxied through to Django either way.

## Rate limits

`/api/` enforces three nginx `limit_req` zones, independent of the pre-existing bot user-agent/subnet throttle (which still runs first and can still hard-block known bad UAs/subnets before any of this is considered):

| Zone | Key | Purpose |
|---|---|---|
| `api_anon_limit` | source IP (`$binary_remote_addr`) | Catches an individual anonymous IP hammering the API. |
| `api_anon_global_limit` | a constant (shared by all anonymous callers) | Catches a *distributed* crawler that spreads load across many source IPs — per-IP limiting alone does ~nothing against a swarm where most IPs fire only once. |
| `api_auth_limit` | the caller's own credential (Bearer token / oauth2-proxy session cookie) | Per-identity limit for authenticated callers, deliberately more generous than the anonymous tiers. Keyed on the raw credential rather than the resolved Keycloak username, because `auth_request_set` variables are only available after nginx's access phase, which runs *after* `limit_req`'s preaccess phase — a zone keyed on the resolved username would silently never limit anyone. |

A request that fails both the website-AJAX check and authentication gets `api_anon_limit` + `api_anon_global_limit` applied; either one tripping returns a 429. An authenticated request gets `api_auth_limit` applied instead. Website AJAX gets neither (empty zone key ⇒ unlimited, the same trick the bot throttle already uses). All three are configured via env vars (see `env.template`); `429`s from any of them return `{"detail":"Rate limit exceeded. Log in for a higher limit."}`.

The anonymous-tier defaults are conservative starting points, not measured capacity limits — tune them against your own app server's actual sustained throughput.

## Testing

Two scripts cover the access-control behavior.

`test_api_access.sh` is a non-interactive smoke test for the nginx routing. It requires no login and checks each access path by sending the headers a browser would set:

```bash
./test_api_access.sh
OMA_BASE_URL=https://yourdomain.com ./test_api_access.sh
```

It verifies that same-origin AJAX (`sec-fetch-site: same-origin` + `sec-fetch-mode: cors`) passes without a token (200) and is never rate-limited, that the crawler pattern found in production (`sec-fetch-site: same-origin` + `sec-fetch-mode: navigate`, no token) is *not* exempted and gets throttled instead, that a plain external client with no token still gets served (just rate-limited, no more 401/redirect), and that `POST /api/auth/device` and `/oma/` pages stay public. It exits non-zero if any check fails, so it can be wired into CI. To also test the authenticated path, pass a token (obtain one with `test_api_auth.sh`):

```bash
OMA_ACCESS_TOKEN=<bearer-token> ./test_api_access.sh
```

`test_api_auth.sh` (see [Script / programmatic access](#script--programmatic-access)) is the interactive end-to-end test of the Bearer-token path through the full device flow.

A few things the smoke test cannot cover and which need a manual check:

- **Real website AJAX.** The smoke test only simulates the Fetch Metadata headers with curl. Confirm the genuine headers work by opening the site in a browser while logged out and verifying that pages whose content loads via API calls still render, with no 429s.
- **Django-level 401s.** `error_page 401 = @api_anon` catches any 401 from the `/api/` location, including one Django itself returns (e.g. authenticated-but-unauthorized). That now means a second proxy_pass to pyoma under the anonymous rate buckets, rather than the old rewritten JSON 401. Check such an endpoint with a valid token and confirm the response is still what you expect.
- **Rate-limit tuning.** The anonymous-tier defaults are conservative starting points. Load-test against a realistic traffic mix before relying on them in production, and adjust `API_ANON_RATE_LIMIT`/`API_ANON_GLOBAL_RATE_LIMIT` (see `env.template`) accordingly.

This is a UX/cost-shaping gate, not a hard security boundary. The Fetch Metadata headers are request headers any client can set (`curl -H "sec-fetch-site: same-origin" -H "sec-fetch-mode: cors" ...` bypasses the free-tier check entirely), so the API contents are effectively public regardless of tier. That is acceptable for public scientific data but should not be relied on to protect anything sensitive.

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

These are exact-match nginx locations that proxy directly to Keycloak and take precedence over the general `/api/` location. They are public (no auth required). All other `/api/` paths go through `auth_request /_auth_check`, which determines the rate-limit tier (website AJAX, authenticated, or anonymous — see "Rate limits") rather than gating access outright.

## Sign-in page branding

The oauth2-proxy sign-in page is only reached when someone deliberately visits `/oauth2/sign_in` (e.g. to get the higher authenticated rate limit) — it's no longer auto-triggered by hitting `/api/` unauthenticated, since anonymous requests are now served directly at the anonymous rate instead of being redirected. Website AJAX and script clients never see it. It is branded for OMA Browser using oauth2-proxy's built-in flags only, set on the `oauth2-proxy` service in `docker-compose.yml`:

| Variable | Effect |
|---|---|
| `OAUTH2_PROXY_CUSTOM_SIGN_IN_LOGO` | Path to the logo shown on the page. The OMA wordmark is mounted into the container from `for_docker/oauth2/logo-oma.svg` (a copy of `oma/static/image/logo-oma.svg` with explicit `width`/`height` added, since oauth2-proxy inlines the SVG and a `viewBox`-only file renders oversized). |
| `OAUTH2_PROXY_PROVIDER_DISPLAY_NAME` | Text in the button, "Sign in with Keycloak". |
| `OAUTH2_PROXY_BANNER` | Heading text above the button. Replaces the default banner, which otherwise renders the `static://200` upstream name. |
| `OAUTH2_PROXY_FOOTER` | Footer HTML. Set to a link back to `omabrowser.org`, replacing the default oauth2-proxy version string. |

Color theming (for example making the button OMA green instead of the oauth2-proxy default teal) is intentionally not done. It would require either a custom Go template (`OAUTH2_PROXY_CUSTOM_TEMPLATES_DIR`), which has to be re-checked against upstream on every version bump, or injecting CSS through the banner, which abuses a content field. Staying with the supported flags keeps the configuration declarative and upgrade-safe.

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
| `API_ANON_RATE_LIMIT` / `API_ANON_RATE_BURST` | Per-source-IP cap for unauthenticated `/api/` callers (see "Rate limits") |
| `API_ANON_GLOBAL_RATE_LIMIT` / `API_ANON_GLOBAL_RATE_BURST` | Aggregate cap shared across all unauthenticated `/api/` callers, regardless of source IP |
| `API_AUTH_RATE_LIMIT` / `API_AUTH_RATE_BURST` | Per-credential cap for authenticated `/api/` callers |
