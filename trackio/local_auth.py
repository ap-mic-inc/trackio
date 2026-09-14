"""Password-based local accounts for self-hosted Trackio dashboards.

Complements the OIDC login (trackio.oidc) with server-managed accounts:

- ``/setup``: first-run page that registers the first admin account. Only
  available while no admin exists anywhere (no stored admin and no
  TRACKIO_OIDC_ADMIN_USERS/GROUPS configured); afterwards it redirects to
  the login page.
- ``/login``: username/password sign-in form. When OIDC is configured, the
  page also offers the OIDC sign-in button.

Local accounts live in the same auth store as OIDC users (sub prefixed with
``local:``), share the same session cookie, and get their permissions from
the role stored on the account (admin / write / read). Admins can create
more local accounts and reset passwords from the Admin page.

Passwords are hashed with scrypt (stdlib), never stored in plaintext.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import secrets

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from trackio import auth_store, oidc

logger = logging.getLogger("trackio.local_auth")

LOGIN_PATH = "/login"
SETUP_PATH = "/setup"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
MIN_PASSWORD_LENGTH = 8

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def validate_new_credentials(username: str, password: str) -> str | None:
    """Return an error message, or None when the credentials are acceptable."""
    if not USERNAME_RE.match(username or ""):
        return "Username must be 2-64 characters: letters, digits, '_', '.', '-'."
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def setup_available() -> bool:
    """The first-run setup page is open only while no admin exists anywhere."""
    config = oidc.load_oidc_config()
    if config is not None and (config.admin_users or config.admin_groups):
        return False
    return not auth_store.has_admin()


def create_local_account(
    username: str, password: str, role: str
) -> tuple[str | None, str | None]:
    """Create a local account with the given role. Returns (sub, error)."""
    error = validate_new_credentials(username, password)
    if error:
        return None, error
    if role not in oidc.ROLE_OVERRIDES:
        return None, "role must be one of: admin, write, read"
    can_write, is_admin = oidc.apply_role_override(False, False, role)
    sub = auth_store.create_local_user(
        username=username,
        password_hash=hash_password(password),
        role=role,
        can_write=can_write,
        is_admin=is_admin,
    )
    if sub is None:
        return None, f"Username {username!r} is already taken."
    return sub, None


def _login_local_user(request: Request, sub: str) -> Response:
    user = auth_store.get_user(sub)
    can_write, is_admin = oidc.apply_role_override(
        False, False, user["role_override"] if user else None
    )
    session = oidc.OidcSession(
        sub=sub,
        email=user["email"] if user else None,
        name=(user["name"] if user else None) or sub,
        username=user["username"] if user else None,
        groups=(),
        can_write=can_write,
        is_admin=is_admin,
    )
    auth_store.record_login(
        sub=session.sub,
        email=session.email,
        name=session.name,
        username=session.username,
        groups=session.groups,
        can_write=session.can_write,
        is_admin=session.is_admin,
    )
    session_id = oidc.install_session(session)
    root = request.scope.get("root_path", "")
    resp = RedirectResponse(url=f"{root}/", status_code=302)
    oidc.set_session_cookie(request, resp, session_id)
    return resp


_PAGE_STYLE = """
  body{font-family:system-ui,sans-serif;display:flex;flex-direction:column;
       align-items:center;padding-top:9vh;margin:0;background:#f5f5f7;color:#111}
  .card{width:320px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;
        padding:28px 28px 22px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
  h1{font-size:18px;margin:0 0 4px} .sub{font-size:13px;color:#6b7280;margin:0 0 18px}
  label{display:block;font-size:12px;color:#6b7280;margin:12px 0 4px}
  input{width:100%;box-sizing:border-box;padding:8px 10px;font-size:14px;
        border:1px solid #d1d5db;border-radius:8px}
  button{width:100%;margin-top:18px;padding:9px;font-size:14px;font-weight:600;
         color:#fff;background:#141c2e;border:none;border-radius:8px;cursor:pointer}
  button:hover{background:#283042}
  .err{margin:14px 0 0;padding:8px 10px;font-size:13px;color:#b91c1c;
       background:#fef2f2;border-radius:8px}
  .alt{margin-top:16px;text-align:center;font-size:13px}
  .alt a{color:#374151}
  .divider{display:flex;align-items:center;gap:10px;margin:16px 0 0;
           color:#9ca3af;font-size:12px}
  .divider::before,.divider::after{content:"";flex:1;height:1px;background:#e5e7eb}
  .oidc-btn{display:block;margin-top:12px;padding:9px;text-align:center;
            font-size:14px;font-weight:600;color:#111;background:#fff;
            border:1px solid #d1d5db;border-radius:8px;text-decoration:none}
  .oidc-btn:hover{border-color:#888}
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)} - Trackio</title>"
        f"<style>{_PAGE_STYLE}</style></head><body>{body}</body></html>"
    )


def _login_page(request: Request, error: str | None = None) -> HTMLResponse:
    root = request.scope.get("root_path", "")
    error_html = f'<p class="err">{html.escape(error)}</p>' if error else ""
    oidc_html = ""
    if oidc.oidc_enabled():
        oidc_html = (
            '<div class="divider">or</div>'
            f'<a class="oidc-btn" href="{root}{oidc.OIDC_START_PATH}">'
            "Sign in with OIDC</a>"
        )
    setup_html = ""
    if setup_available():
        setup_html = (
            f'<p class="alt">First time here? '
            f'<a href="{root}{SETUP_PATH}">Create the admin account</a></p>'
        )
    return _page(
        "Sign in",
        f"""<div class="card">
        <h1>Sign in to Trackio</h1>
        <p class="sub">Use your local account credentials.</p>
        <form method="post" action="{root}{LOGIN_PATH}">
          <label for="username">Username</label>
          <input id="username" name="username" autocomplete="username" autofocus>
          <label for="password">Password</label>
          <input id="password" name="password" type="password"
                 autocomplete="current-password">
          {error_html}
          <button type="submit">Sign in</button>
        </form>
        {oidc_html}
        </div>{setup_html}""",
    )


def _setup_page(request: Request, error: str | None = None) -> HTMLResponse:
    root = request.scope.get("root_path", "")
    error_html = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return _page(
        "Set up admin",
        f"""<div class="card">
        <h1>Create the admin account</h1>
        <p class="sub">This server has no administrator yet. Register the
        first (admin) account to manage users and permissions.</p>
        <form method="post" action="{root}{SETUP_PATH}">
          <label for="username">Username</label>
          <input id="username" name="username" autocomplete="username" autofocus>
          <label for="password">Password (min {MIN_PASSWORD_LENGTH} characters)</label>
          <input id="password" name="password" type="password"
                 autocomplete="new-password">
          <label for="confirm">Confirm password</label>
          <input id="confirm" name="confirm" type="password"
                 autocomplete="new-password">
          {error_html}
          <button type="submit">Create admin account</button>
        </form>
        <p class="alt"><a href="{root}{LOGIN_PATH}">Back to sign in</a></p>
        </div>""",
    )


async def login_get(request: Request) -> Response:
    if oidc.get_oidc_session(request) is not None:
        root = request.scope.get("root_path", "")
        return RedirectResponse(url=f"{root}/", status_code=302)
    return _login_page(request)


async def login_post(request: Request) -> Response:
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    sub = f"{auth_store.LOCAL_SUB_PREFIX}{username}"
    stored = auth_store.get_password_hash(sub) if username else None
    if not verify_password(password, stored):
        logger.warning("local sign-in failed for username=%r", username)
        return _login_page(request, error="Invalid username or password.")
    return _login_local_user(request, sub)


async def setup_get(request: Request) -> Response:
    root = request.scope.get("root_path", "")
    if not setup_available():
        return RedirectResponse(url=f"{root}{LOGIN_PATH}", status_code=302)
    return _setup_page(request)


async def setup_post(request: Request) -> Response:
    root = request.scope.get("root_path", "")
    if not setup_available():
        return RedirectResponse(url=f"{root}{LOGIN_PATH}", status_code=302)
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    confirm = str(form.get("confirm") or "")
    if password != confirm:
        return _setup_page(request, error="Passwords do not match.")
    sub, error = create_local_account(username, password, "admin")
    if error:
        return _setup_page(request, error=error)
    logger.warning("First admin account %r created via /setup.", username)
    return _login_local_user(request, sub)


def local_auth_routes() -> list[Route]:
    return [
        Route(LOGIN_PATH, login_get, methods=["GET"]),
        Route(LOGIN_PATH, login_post, methods=["POST"]),
        Route(SETUP_PATH, setup_get, methods=["GET"]),
        Route(SETUP_PATH, setup_post, methods=["POST"]),
    ]
