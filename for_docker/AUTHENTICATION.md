# API Authentication

The OMA Browser REST API (`/api/`) is protected by [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) integrated with Keycloak. Public paths (`/oma/`, `/static/`, `/media/`) require no authentication.

## Architecture

```
internet → oauth2-proxy:80 → nginx:80 → web:8000
```

oauth2-proxy is the public entry point. Nginx is internal only (not exposed on the host).

## Access patterns

### Browser

Navigate to any `/api/` URL. You will be redirected to Keycloak to log in, then returned to the original URL automatically.

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
2. Click on `<your-client-id>-dedicated` (e.g. `omabrowser-dedicated`) — it is a hyperlink
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

These endpoints are public (no auth required). All other `/api/` paths require a valid token.

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
