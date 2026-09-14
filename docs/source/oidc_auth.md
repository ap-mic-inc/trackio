# OIDC Authentication (Self-hosted)

A self-hosted Trackio server can require sign-in through any OpenID Connect provider (Keycloak, Authentik, Google, Microsoft Entra ID, Okta, ...) and map signed-in users to read or write permissions. This complements the [write token](self_hosted_server.md): training scripts keep authenticating with `TRACKIO_WRITE_TOKEN`, while humans use the browser sign-in flow.

## Enable OIDC login

Register a **confidential client** at your identity provider with the redirect URI:

```
https://your-trackio-host/oauth/oidc/callback
```

Then set these environment variables on the server before launching `trackio show`:

```bash
export TRACKIO_OIDC_ISSUER="https://idp.example.com/realms/main"
export TRACKIO_OIDC_CLIENT_ID="trackio"
export TRACKIO_OIDC_CLIENT_SECRET="..."
```

The provider's endpoints are discovered automatically from `{issuer}/.well-known/openid-configuration`. The login flow uses the authorization code flow with PKCE. A "Sign in" button appears in the dashboard sidebar; sessions last 30 days and are kept in server memory (a restart signs everyone out).

## Permissions

Two levels exist: **read** (view dashboards) and **write** (log metrics, upload files, delete or rename runs).

| Variable | Meaning |
|---|---|
| `TRACKIO_OIDC_ALLOWED_USERS` | Comma-separated emails/usernames/subs allowed to sign in. Empty = anyone the provider authenticates. |
| `TRACKIO_OIDC_ALLOWED_GROUPS` | Groups allowed to sign in (OR-combined with `ALLOWED_USERS`). |
| `TRACKIO_OIDC_WRITE_USERS` | Emails/usernames/subs granted write access. `*` = every signed-in user. |
| `TRACKIO_OIDC_WRITE_GROUPS` | Groups granted write access. |
| `TRACKIO_OIDC_GROUPS_CLAIM` | Claim that holds the user's groups (default `groups`). |
| `TRACKIO_OIDC_SCOPES` | Requested scopes (default `openid profile email`). |

If neither `TRACKIO_OIDC_WRITE_USERS` nor `TRACKIO_OIDC_WRITE_GROUPS` is set, every signed-in user gets write access. When they are set, other signed-in users are read-only. Matching is case-insensitive against the `email`, `preferred_username`, and `sub` claims.

Example — anyone in the company may view, only two people may write:

```bash
export TRACKIO_OIDC_WRITE_USERS="alice@example.com,bob@example.com"
```

Example — group-based via a Keycloak `groups` claim:

```bash
export TRACKIO_OIDC_ALLOWED_GROUPS="ml-team"
export TRACKIO_OIDC_WRITE_GROUPS="ml-admins"
```

## Require sign-in for everything

By default only writes are protected and dashboards stay publicly viewable. To put the whole dashboard (all pages and read APIs) behind sign-in:

```bash
export TRACKIO_AUTH_REQUIRED=1
```

Browser requests without a session are redirected to the sign-in flow; API requests receive `401`. Requests that carry a valid write token (`X-Trackio-Write-Token` header, cookie, or `?write_token=` query parameter) bypass the gate, so training scripts continue to work unchanged.

## Other options

| Variable | Meaning |
|---|---|
| `TRACKIO_OIDC_REDIRECT_BASE` | External base URL used to build the callback URI when the server sits behind a reverse proxy (e.g. `https://trackio.example.com`). Defaults to the request's own base URL. |
| `TRACKIO_OIDC_COOKIE_SECURE` | Force the `Secure` flag on the session cookie (`1`/`0`). Defaults to on when the request arrived over HTTPS (honors `X-Forwarded-Proto`). |

## How it interacts with the write token

| Actor | Credential | Access |
|---|---|---|
| Training script | `TRACKIO_WRITE_TOKEN` / write-token URL | Full write, bypasses `TRACKIO_AUTH_REQUIRED` |
| Signed-in user with write permission | OIDC session cookie | Full write from the dashboard |
| Signed-in user without write permission | OIDC session cookie | Read-only |
| Anonymous visitor | none | Read-only, or nothing when `TRACKIO_AUTH_REQUIRED=1` |

## Related

- [Self-host the Server](self_hosted_server.md)
- [Environment Variables](environment_variables.md)
