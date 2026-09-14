"""Generic OIDC authentication for self-hosted Trackio dashboards.

Enables login against any OpenID Connect provider (Keycloak, Authentik,
Google, Entra ID, ...) via the authorization code flow with PKCE, and maps
authenticated users to read/write permissions.

Configuration (environment variables):

- TRACKIO_OIDC_ISSUER: issuer URL; enables OIDC when set. Discovery document
  is fetched from ``{issuer}/.well-known/openid-configuration``.
- TRACKIO_OIDC_CLIENT_ID / TRACKIO_OIDC_CLIENT_SECRET: client credentials.
- TRACKIO_OIDC_SCOPES: requested scopes (default: ``openid profile email``).
- TRACKIO_OIDC_ALLOWED_USERS: comma-separated emails/usernames/subs allowed
  to sign in. Empty means every user the provider authenticates may sign in.
- TRACKIO_OIDC_ALLOWED_GROUPS: comma-separated groups allowed to sign in
  (checked against the groups claim). Combined with ALLOWED_USERS as OR.
- TRACKIO_OIDC_WRITE_USERS: comma-separated emails/usernames/subs granted
  write access. ``*`` grants write to every signed-in user.
- TRACKIO_OIDC_WRITE_GROUPS: comma-separated groups granted write access.
- TRACKIO_OIDC_ADMIN_USERS / TRACKIO_OIDC_ADMIN_GROUPS: users/groups granted
  admin access (the Admin page in the dashboard). Admins always have write
  access. Anyone with the server write token is also an admin.
- TRACKIO_OIDC_FIRST_USER_ADMIN: when no admin is configured or stored, the
  first user to sign in is promoted to admin (default on; set 0 to disable).
  Admins can also assign roles from the Admin page; those stored overrides
  take precedence over the environment lists.
- TRACKIO_OIDC_GROUPS_CLAIM: claim holding the user's groups (default:
  ``groups``).
- TRACKIO_AUTH_REQUIRED: when truthy, every dashboard/API request requires a
  signed-in OIDC session (requests carrying a valid write token are exempt so
  training scripts keep working).
- TRACKIO_OIDC_COOKIE_SECURE: force the Secure flag on the session cookie
  (defaults to on when the request arrived over https).

If neither WRITE_USERS nor WRITE_GROUPS is configured, every signed-in user
gets write access.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from trackio import auth_store

logger = logging.getLogger("trackio.oidc")

OIDC_START_PATH = "/oauth/oidc/start"
OIDC_CALLBACK_PATH = "/oauth/oidc/callback"
OIDC_SESSION_COOKIE = "trackio_oidc_session"

_STATE_TTL = 600
_SESSION_TTL = 86400 * 30
_DISCOVERY_TTL = 3600


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _csv_set(value: str | None) -> frozenset[str]:
    return frozenset(
        item.strip().lower() for item in (value or "").split(",") if item.strip()
    )


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    scopes: str
    allowed_users: frozenset[str]
    allowed_groups: frozenset[str]
    write_users: frozenset[str]
    write_groups: frozenset[str]
    admin_users: frozenset[str]
    admin_groups: frozenset[str]
    groups_claim: str
    auth_required: bool
    cookie_secure: bool | None
    first_user_admin: bool

    @property
    def write_open_to_all(self) -> bool:
        return not self.write_users and not self.write_groups


def load_oidc_config() -> OidcConfig | None:
    issuer = (os.environ.get("TRACKIO_OIDC_ISSUER") or "").strip().rstrip("/")
    if not issuer:
        return None
    client_id = (os.environ.get("TRACKIO_OIDC_CLIENT_ID") or "").strip()
    if not client_id:
        logger.warning(
            "TRACKIO_OIDC_ISSUER is set but TRACKIO_OIDC_CLIENT_ID is missing; "
            "OIDC login is disabled."
        )
        return None
    cookie_secure_env = os.environ.get("TRACKIO_OIDC_COOKIE_SECURE")
    return OidcConfig(
        issuer=issuer,
        client_id=client_id,
        client_secret=(os.environ.get("TRACKIO_OIDC_CLIENT_SECRET") or "").strip(),
        scopes=(
            os.environ.get("TRACKIO_OIDC_SCOPES") or "openid profile email"
        ).strip(),
        allowed_users=_csv_set(os.environ.get("TRACKIO_OIDC_ALLOWED_USERS")),
        allowed_groups=_csv_set(os.environ.get("TRACKIO_OIDC_ALLOWED_GROUPS")),
        write_users=_csv_set(os.environ.get("TRACKIO_OIDC_WRITE_USERS")),
        write_groups=_csv_set(os.environ.get("TRACKIO_OIDC_WRITE_GROUPS")),
        admin_users=_csv_set(os.environ.get("TRACKIO_OIDC_ADMIN_USERS")),
        admin_groups=_csv_set(os.environ.get("TRACKIO_OIDC_ADMIN_GROUPS")),
        groups_claim=(os.environ.get("TRACKIO_OIDC_GROUPS_CLAIM") or "groups").strip(),
        auth_required=_truthy(os.environ.get("TRACKIO_AUTH_REQUIRED")),
        cookie_secure=(
            None if cookie_secure_env is None else _truthy(cookie_secure_env)
        ),
        first_user_admin=_truthy(os.environ.get("TRACKIO_OIDC_FIRST_USER_ADMIN", "1")),
    )


def oidc_enabled() -> bool:
    return load_oidc_config() is not None


def auth_required() -> bool:
    config = load_oidc_config()
    return bool(config and config.auth_required)


@dataclass
class OidcSession:
    sub: str
    email: str | None
    name: str | None
    username: str | None
    groups: tuple[str, ...]
    can_write: bool
    is_admin: bool = False
    created: float = field(default_factory=time.monotonic)

    @property
    def display_name(self) -> str:
        return self.name or self.username or self.email or self.sub


_sessions: dict[str, OidcSession] = {}
_pending_states: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()

_discovery_cache: tuple[str, dict[str, Any], float] | None = None


def _evict_expired() -> None:
    now = time.monotonic()
    with _lock:
        for key in [k for k, (_, t) in _pending_states.items() if now - t > _STATE_TTL]:
            del _pending_states[key]
        for key in [k for k, s in _sessions.items() if now - s.created > _SESSION_TTL]:
            del _sessions[key]


def _discover(issuer: str) -> dict[str, Any]:
    global _discovery_cache
    now = time.monotonic()
    if _discovery_cache is not None:
        cached_issuer, doc, fetched = _discovery_cache
        if cached_issuer == issuer and now - fetched < _DISCOVERY_TTL:
            return doc
    url = f"{issuer}/.well-known/openid-configuration"
    with httpx.Client(timeout=10) as client:
        resp = client.get(url)
        resp.raise_for_status()
        doc = resp.json()
    _discovery_cache = (issuer, doc, now)
    return doc


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode the payload of a JWT without signature verification.

    Only used on id_tokens received directly from the provider's token
    endpoint over TLS with client authentication, where the transport itself
    authenticates the issuer.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _identity_values(claims: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("email", "preferred_username", "sub"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            values.add(value.strip().lower())
    return values


def _claim_groups(claims: dict[str, Any], groups_claim: str) -> tuple[str, ...]:
    raw = claims.get(groups_claim)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())


def evaluate_permissions(
    config: OidcConfig, claims: dict[str, Any]
) -> tuple[bool, bool, bool]:
    """Return (allowed_to_sign_in, can_write, is_admin) for the given claims.

    Admins always have write access. Admins configured via
    TRACKIO_OIDC_ADMIN_USERS/GROUPS may sign in even when not listed in the
    allowed users/groups.
    """
    identities = _identity_values(claims)
    groups = {g.lower() for g in _claim_groups(claims, config.groups_claim)}

    is_admin = bool(identities & config.admin_users) or bool(
        groups & config.admin_groups
    )

    if config.allowed_users or config.allowed_groups:
        allowed = (
            is_admin
            or bool(identities & config.allowed_users)
            or bool(groups & config.allowed_groups)
        )
    else:
        allowed = True
    if not allowed:
        return False, False, False

    if is_admin or config.write_open_to_all:
        return True, True, is_admin
    can_write = (
        "*" in config.write_users
        or bool(identities & config.write_users)
        or bool(groups & config.write_groups)
    )
    return True, can_write, is_admin


ROLE_OVERRIDES = ("admin", "write", "read")


def apply_role_override(
    can_write: bool, is_admin: bool, override: str | None
) -> tuple[bool, bool]:
    """Map a stored role override onto (can_write, is_admin)."""
    if override == "admin":
        return True, True
    if override == "write":
        return True, False
    if override == "read":
        return False, False
    return can_write, is_admin


def resolve_login_permissions(
    config: OidcConfig, claims: dict[str, Any]
) -> tuple[bool, bool, bool, bool]:
    """Return (allowed, can_write, is_admin, bootstrapped) for a sign-in.

    Combines the environment-based evaluation with any role override stored
    by an admin (an override also allows sign-in, since the user was
    explicitly managed). When no admin is configured anywhere, the first
    user to sign in is promoted to admin unless
    TRACKIO_OIDC_FIRST_USER_ADMIN=0.
    """
    allowed, can_write, is_admin = evaluate_permissions(config, claims)

    sub = claims.get("sub")
    override = auth_store.get_role_override(sub) if isinstance(sub, str) else None
    if override in ROLE_OVERRIDES:
        can_write, is_admin = apply_role_override(can_write, is_admin, override)
        return True, can_write, is_admin, False

    if not allowed:
        return False, False, False, False

    if (
        config.first_user_admin
        and not is_admin
        and not config.admin_users
        and not config.admin_groups
        and not auth_store.has_admin()
    ):
        return True, True, True, True

    return True, can_write, is_admin, False


def refresh_user_permissions(sub: str) -> dict[str, bool] | None:
    """Recompute a user's permissions from the current configuration and
    stored role override, then apply them to the users table and any live
    sessions. Returns the new permissions, or None if the user is unknown."""
    user = auth_store.get_user(sub)
    if user is None:
        return None
    config = load_oidc_config()
    if config is not None:
        claims = {
            "sub": sub,
            "email": user["email"],
            "preferred_username": user["username"],
            config.groups_claim: list(user["groups"]),
        }
        _, can_write, is_admin = evaluate_permissions(config, claims)
    else:
        can_write = is_admin = False
    can_write, is_admin = apply_role_override(
        can_write, is_admin, user["role_override"]
    )
    auth_store.update_user_permissions(sub, can_write, is_admin)
    with _lock:
        for session in _sessions.values():
            if session.sub == sub:
                session.can_write = can_write
                session.is_admin = is_admin
    return {"can_write": can_write, "is_admin": is_admin}


def _root_path(request: Request) -> str:
    return request.scope.get("root_path", "")


def _callback_uri(request: Request) -> str:
    base = (os.environ.get("TRACKIO_OIDC_REDIRECT_BASE") or "").strip().rstrip("/")
    if base:
        return f"{base}{OIDC_CALLBACK_PATH}"
    return str(request.base_url).rstrip("/") + OIDC_CALLBACK_PATH


def _cookie_secure(request: Request, config: OidcConfig) -> bool:
    if config.cookie_secure is not None:
        return config.cookie_secure
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.split(",")[0].strip() == "https"


def get_oidc_session(request: Request) -> OidcSession | None:
    cookie_header = ""
    try:
        cookie_header = request.headers.get("cookie", "") or ""
    except (AttributeError, TypeError):
        return None
    session_id = None
    for cookie in cookie_header.split(";"):
        parts = cookie.strip().split("=", 1)
        if len(parts) == 2 and parts[0] == OIDC_SESSION_COOKIE:
            session_id = parts[1]
            break
    if not session_id:
        return None
    with _lock:
        session = _sessions.get(session_id)
    if session is not None:
        if time.monotonic() - session.created > _SESSION_TTL:
            with _lock:
                _sessions.pop(session_id, None)
            auth_store.delete_session(session_id)
            return None
        return session
    return _restore_persisted_session(session_id)


def _restore_persisted_session(session_id: str) -> OidcSession | None:
    stored = auth_store.load_session(session_id, _SESSION_TTL)
    if stored is None:
        return None
    session = OidcSession(
        sub=stored["sub"],
        email=stored["email"],
        name=stored["name"],
        username=stored["username"],
        groups=stored["groups"],
        can_write=stored["can_write"],
        is_admin=stored["is_admin"],
        created=time.monotonic() - stored["age"],
    )
    with _lock:
        _sessions[session_id] = session
    return session


def drop_session(request: Request) -> None:
    cookie_header = ""
    try:
        cookie_header = request.headers.get("cookie", "") or ""
    except (AttributeError, TypeError):
        return
    for cookie in cookie_header.split(";"):
        parts = cookie.strip().split("=", 1)
        if len(parts) == 2 and parts[0] == OIDC_SESSION_COOKIE:
            with _lock:
                _sessions.pop(parts[1], None)
            auth_store.delete_session(parts[1])


def revoke_sessions_for_sub(sub: str) -> int:
    revoked_ids = set(auth_store.delete_sessions_for_sub(sub))
    with _lock:
        for session_id in [
            k for k, s in _sessions.items() if s.sub == sub or k in revoked_ids
        ]:
            revoked_ids.add(session_id)
            del _sessions[session_id]
    return len(revoked_ids)


def oidc_start(request: Request) -> Response:
    config = load_oidc_config()
    if config is None:
        return RedirectResponse(url=f"{_root_path(request)}/", status_code=302)
    _evict_expired()
    try:
        doc = _discover(config.issuer)
        authorization_endpoint = doc["authorization_endpoint"]
    except Exception as e:
        logger.error("OIDC discovery failed: %s", e)
        return RedirectResponse(
            url=f"{_root_path(request)}/?oidc_error=discovery", status_code=302
        )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    with _lock:
        _pending_states[state] = (verifier, time.monotonic())
    params = {
        "client_id": config.client_id,
        "redirect_uri": _callback_uri(request),
        "response_type": "code",
        "scope": config.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(
        url=f"{authorization_endpoint}?{urlencode(params)}", status_code=302
    )


def oidc_callback(request: Request) -> Response:
    config = load_oidc_config()
    err = f"{_root_path(request)}/?oidc_error=1"
    if config is None:
        return RedirectResponse(url=err, status_code=302)
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        return RedirectResponse(url=err, status_code=302)
    with _lock:
        pending = _pending_states.pop(state, None)
    if pending is None:
        return RedirectResponse(url=err, status_code=302)
    verifier, created = pending
    if time.monotonic() - created > _STATE_TTL:
        return RedirectResponse(url=err, status_code=302)

    try:
        doc = _discover(config.issuer)
        token_endpoint = doc["token_endpoint"]
        userinfo_endpoint = doc.get("userinfo_endpoint")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _callback_uri(request),
            "client_id": config.client_id,
            "code_verifier": verifier,
        }
        headers = {}
        if config.client_secret:
            auth_b64 = base64.b64encode(
                f"{config.client_id}:{config.client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {auth_b64}"
        with httpx.Client(timeout=15) as client:
            token_resp = client.post(token_endpoint, data=data, headers=headers)
            token_resp.raise_for_status()
            tokens = token_resp.json()
            claims = _decode_jwt_claims(tokens.get("id_token", ""))
            access_token = tokens.get("access_token")
            if userinfo_endpoint and access_token:
                try:
                    userinfo_resp = client.get(
                        userinfo_endpoint,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    userinfo_resp.raise_for_status()
                    userinfo = userinfo_resp.json()
                    if isinstance(userinfo, dict):
                        claims = {**claims, **userinfo}
                except Exception as e:
                    logger.warning("OIDC userinfo request failed: %s", e)
    except Exception as e:
        logger.error("OIDC token exchange failed: %s", e)
        return RedirectResponse(url=err, status_code=302)

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        return RedirectResponse(url=err, status_code=302)

    allowed, can_write, is_admin, bootstrapped = resolve_login_permissions(
        config, claims
    )
    if not allowed:
        logger.warning("OIDC sign-in denied for sub=%s", sub)
        return RedirectResponse(
            url=f"{_root_path(request)}/?oidc_error=forbidden", status_code=302
        )

    session = OidcSession(
        sub=sub,
        email=claims.get("email"),
        name=claims.get("name"),
        username=claims.get("preferred_username"),
        groups=_claim_groups(claims, config.groups_claim),
        can_write=can_write,
        is_admin=is_admin,
    )
    session_id = secrets.token_urlsafe(32)
    with _lock:
        _sessions[session_id] = session
    _evict_expired()
    auth_store.record_login(
        sub=session.sub,
        email=session.email,
        name=session.name,
        username=session.username,
        groups=session.groups,
        can_write=session.can_write,
        is_admin=session.is_admin,
    )
    if bootstrapped:
        auth_store.set_role_override(session.sub, "admin")
        logger.warning(
            "First OIDC user %s was promoted to admin (disable with "
            "TRACKIO_OIDC_FIRST_USER_ADMIN=0).",
            session.display_name,
        )
    auth_store.persist_session(session_id, session.sub)

    resp = RedirectResponse(url=f"{_root_path(request)}/", status_code=302)
    resp.set_cookie(
        key=OIDC_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=_SESSION_TTL,
        path="/",
        secure=_cookie_secure(request, config),
    )
    return resp


def clear_session_cookie(request: Request, resp: Response) -> None:
    drop_session(request)
    config = load_oidc_config()
    secure = _cookie_secure(request, config) if config else False
    resp.delete_cookie(
        OIDC_SESSION_COOKIE,
        path="/",
        samesite="lax",
        secure=secure,
    )


def oidc_routes() -> list[Route]:
    return [
        Route(OIDC_START_PATH, oidc_start, methods=["GET"]),
        Route(OIDC_CALLBACK_PATH, oidc_callback, methods=["GET"]),
    ]


_AUTH_EXEMPT_PATHS = frozenset(
    {
        OIDC_START_PATH,
        OIDC_CALLBACK_PATH,
        "/oauth/logout",
        "/oauth/hf/start",
        "/login/callback",
        "/version",
    }
)


class OidcAuthRequiredMiddleware:
    """Gates the whole app behind an OIDC session when TRACKIO_AUTH_REQUIRED
    is set. Requests carrying a valid write token bypass the gate so training
    clients keep working without a browser session.
    """

    def __init__(self, app: Any, write_token_checker: Any) -> None:
        self.app = app
        self.write_token_checker = write_token_checker

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not auth_required():
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or "/"
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path) :] or "/"
        if path in _AUTH_EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        if get_oidc_session(request) is not None:
            await self.app(scope, receive, send)
            return
        if self.write_token_checker(request):
            await self.app(scope, receive, send)
            return
        if path.startswith("/api/") or path.startswith("/gradio_api/"):
            resp: Response = JSONResponse(
                {"error": "Authentication required. Sign in via OIDC."},
                status_code=401,
            )
        else:
            resp = RedirectResponse(
                url=f"{root_path}{OIDC_START_PATH}", status_code=302
            )
        await resp(scope, receive, send)
