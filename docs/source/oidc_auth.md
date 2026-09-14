# Authentication (Self-hosted)

A self-hosted Trackio server supports two kinds of browser sign-in, sharing one session and permission system:

- **Local accounts**: username/password accounts managed by the server itself, starting with a first-run `/setup` page that registers the admin account.
- **OIDC**: sign-in through any OpenID Connect provider (Keycloak, Authentik, Google, Microsoft Entra ID, Okta, ...).

Both complement the [write token](self_hosted_server.md): training scripts keep authenticating with `TRACKIO_WRITE_TOKEN`, while humans use the browser sign-in flow.

## Local accounts & first-run setup

A fresh server needs no configuration to get an administrator:

1. Open the dashboard and click **Sign in** (or visit `/setup` directly).
2. While the server has no admin anywhere, the setup page lets you **register the first admin account** (username + password). It signs you in immediately and the setup page closes permanently.
3. From the Admin tab you can then create more local accounts (username, password, role) and reset their passwords. Local users sign in at `/login`.

Local accounts are stored in `TRACKIO_DIR/auth/auth.db` with scrypt-hashed passwords. The `/login` page also shows a "Sign in with OIDC" button whenever OIDC is configured, so both kinds of users share one entry point. The setup page is disabled when `TRACKIO_OIDC_ADMIN_USERS`/`TRACKIO_OIDC_ADMIN_GROUPS` are configured (the environment already defines the admins).

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

The provider's endpoints are discovered automatically from `{issuer}/.well-known/openid-configuration`. The login flow uses the authorization code flow with PKCE. A "Sign in" button appears in the dashboard sidebar; sessions last 30 days and are persisted in `TRACKIO_DIR/auth/auth.db`, so they survive server restarts.

## Permissions

Two levels exist: **read** (view dashboards) and **write** (log metrics, upload files, delete or rename runs).

| Variable | Meaning |
|---|---|
| `TRACKIO_OIDC_ALLOWED_USERS` | Comma-separated emails/usernames/subs allowed to sign in. Empty = anyone the provider authenticates. |
| `TRACKIO_OIDC_ALLOWED_GROUPS` | Groups allowed to sign in (OR-combined with `ALLOWED_USERS`). |
| `TRACKIO_OIDC_WRITE_USERS` | Emails/usernames/subs granted write access. `*` = every signed-in user. |
| `TRACKIO_OIDC_WRITE_GROUPS` | Groups granted write access. |
| `TRACKIO_OIDC_ADMIN_USERS` | Emails/usernames/subs granted admin access (see [Admin page](#admin-page)). Admins always have write access and may sign in even when not in the allowed lists. |
| `TRACKIO_OIDC_ADMIN_GROUPS` | Groups granted admin access. |
| `TRACKIO_OIDC_FIRST_USER_ADMIN` | Opt-in (`1`): promote the first OIDC sign-in to admin when no admin exists anywhere. Default off — the first admin is registered on the `/setup` page instead. |
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

## Admin page

Admins see an **Admin** tab in the dashboard navbar showing:

- Every user who has signed in via OIDC: name, email, resolved access level (admin / write / read-only), last login, login count, and active sessions.
- Per user, the projects they have written to (metric logging, uploads, artifacts, run management), with first/last activity timestamps. High-frequency logging is aggregated to one count per minute per project.
- Projects written by scripts using the server write token (these have no user identity).
- A **Sign out** button per user that revokes all of that user's sessions immediately.

Who is an admin:

- **The account registered on the first-run `/setup` page** (see [Local accounts](#local-accounts--first-run-setup)).
- Optionally, the first user to sign in via OIDC, when `TRACKIO_OIDC_FIRST_USER_ADMIN=1` is set and no admin exists anywhere.
- Users/groups listed in `TRACKIO_OIDC_ADMIN_USERS` / `TRACKIO_OIDC_ADMIN_GROUPS`.
- Anyone assigned the admin role from the Admin page (see below).
- Anyone with the server write token (the write-access URL from `trackio.show()`), so the server owner always has access even before OIDC is configured.

## Managing roles from the UI

Each user row on the Admin page has a **Role** selector: `default (env)`, `admin`, `write`, or `read-only`. A selected role is stored in the database and overrides the environment-based permissions for that user; `default (env)` falls back to the `TRACKIO_OIDC_*` lists. Changes take effect immediately, including for the user's active sessions — demoting someone to read-only blocks their next write. A stored role also lets the user sign in even when they are not in the allowed lists.

All of this data lives in `TRACKIO_DIR/auth/auth.db` and survives restarts. The underlying APIs are `admin_get_users`, `admin_set_role`, and `admin_revoke_user_sessions`.

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
