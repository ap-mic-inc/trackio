"""SQLite persistence for OIDC users, sessions, and write activity.

Backs the admin page of a self-hosted server: which users have signed in,
what permissions they resolved to, which projects each actor has written to,
and which sessions are active. Lives in ``TRACKIO_DIR/auth.db`` so it
survives server restarts (unlike the in-memory session cache it backs).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trackio import utils

logger = logging.getLogger("trackio.auth_store")

WRITE_TOKEN_ACTOR = "__write_token__"

_ACTIVITY_THROTTLE_SECONDS = 60.0

_lock = threading.Lock()
_last_activity_write: dict[tuple[str, str, str], float] = {}

_SETTINGS_CACHE_TTL = 5.0
_settings_cache: dict[str, tuple[Any, float]] = {}

API_TOKEN_PREFIX = "trk_"
_API_TOKEN_CACHE_TTL = 10.0
_API_TOKEN_TOUCH_INTERVAL = 60.0
_api_token_cache: dict[str, tuple[dict[str, Any] | None, float]] = {}
_api_token_last_touch: dict[str, float] = {}


def _db_path() -> Path:
    return utils.TRACKIO_DIR / "auth" / "auth.db"


def _connect() -> sqlite3.Connection:
    _db_path().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            sub TEXT PRIMARY KEY,
            email TEXT,
            name TEXT,
            username TEXT,
            groups_json TEXT,
            can_write INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            first_login TEXT,
            last_login TEXT,
            login_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
    if "role_override" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN role_override TEXT")
    if "password_hash" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            sub TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actor_projects (
            actor TEXT NOT NULL,
            project TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            PRIMARY KEY (actor, project, action)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_tokens (
            id TEXT PRIMARY KEY,
            sub TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            hint TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS api_tokens_sub ON api_tokens (sub)")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def get_setting(key: str) -> Any | None:
    """Read a JSON settings value. Results are cached briefly, since this is
    called on the request path (auth gate, config resolution)."""
    now = time.monotonic()
    with _lock:
        cached = _settings_cache.get(key)
        if cached is not None and now - cached[1] < _SETTINGS_CACHE_TTL:
            return cached[0]
    value: Any | None = None
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                value = json.loads(row[0])
    except (sqlite3.Error, ValueError) as e:
        logger.warning("failed to read setting %s: %s", key, e)
        return None
    with _lock:
        _settings_cache[key] = (value, now)
    return value


def set_setting(key: str, value: Any) -> None:
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, json.dumps(value)),
            )
            _settings_cache.pop(key, None)
    except sqlite3.Error as e:
        logger.warning("failed to write setting %s: %s", key, e)


def record_login(
    sub: str,
    email: str | None,
    name: str | None,
    username: str | None,
    groups: tuple[str, ...],
    can_write: bool,
    is_admin: bool,
) -> None:
    now = _now_iso()
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    sub, email, name, username, groups_json,
                    can_write, is_admin, first_login, last_login, login_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(sub) DO UPDATE SET
                    email=excluded.email,
                    name=excluded.name,
                    username=excluded.username,
                    groups_json=excluded.groups_json,
                    can_write=excluded.can_write,
                    is_admin=excluded.is_admin,
                    last_login=excluded.last_login,
                    login_count=login_count + 1
                """,
                (
                    sub,
                    email,
                    name,
                    username,
                    json.dumps(list(groups)),
                    int(can_write),
                    int(is_admin),
                    now,
                    now,
                ),
            )
    except sqlite3.Error as e:
        logger.warning("failed to record login for %s: %s", sub, e)


def get_user(sub: str) -> dict[str, Any] | None:
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                """
                SELECT sub, email, name, username, groups_json, can_write,
                       is_admin, role_override
                FROM users WHERE sub = ?
                """,
                (sub,),
            ).fetchone()
    except sqlite3.Error as e:
        logger.warning("failed to get user %s: %s", sub, e)
        return None
    if row is None:
        return None
    return {
        "sub": row[0],
        "email": row[1],
        "name": row[2],
        "username": row[3],
        "groups": tuple(json.loads(row[4] or "[]")),
        "can_write": bool(row[5]),
        "is_admin": bool(row[6]),
        "role_override": row[7],
    }


def get_role_override(sub: str) -> str | None:
    user = get_user(sub)
    return user["role_override"] if user else None


LOCAL_SUB_PREFIX = "local:"


def is_local_sub(sub: str) -> bool:
    return sub.startswith(LOCAL_SUB_PREFIX)


def create_local_user(
    username: str,
    password_hash: str,
    role: str,
    can_write: bool,
    is_admin: bool,
) -> str | None:
    """Create a password-based local account. Returns the new sub, or None
    when the username is already taken."""
    sub = f"{LOCAL_SUB_PREFIX}{username}"
    now = _now_iso()
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    sub, username, name, groups_json, can_write, is_admin,
                    role_override, password_hash, first_login, login_count
                )
                VALUES (?, ?, ?, '[]', ?, ?, ?, ?, ?, 0)
                """,
                (
                    sub,
                    username,
                    username,
                    int(can_write),
                    int(is_admin),
                    role,
                    password_hash,
                    now,
                ),
            )
    except sqlite3.IntegrityError:
        return None
    except sqlite3.Error as e:
        logger.warning("failed to create local user %s: %s", username, e)
        return None
    return sub


def get_password_hash(sub: str) -> str | None:
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE sub = ?", (sub,)
            ).fetchone()
            return row[0] if row else None
    except sqlite3.Error as e:
        logger.warning("failed to get password hash for %s: %s", sub, e)
        return None


def set_password_hash(sub: str, password_hash: str) -> bool:
    try:
        with _lock, _connect() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE sub = ?",
                (password_hash, sub),
            )
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.warning("failed to set password hash for %s: %s", sub, e)
        return False


def set_role_override(sub: str, role: str | None) -> None:
    """Store a role override for ``sub``, creating a stub user row when the
    user has not signed in yet."""
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (sub, role_override) VALUES (?, ?)
                ON CONFLICT(sub) DO UPDATE SET role_override=excluded.role_override
                """,
                (sub, role),
            )
    except sqlite3.Error as e:
        logger.warning("failed to set role override for %s: %s", sub, e)


def update_user_permissions(sub: str, can_write: bool, is_admin: bool) -> None:
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "UPDATE users SET can_write = ?, is_admin = ? WHERE sub = ?",
                (int(can_write), int(is_admin), sub),
            )
            _api_token_cache.clear()
    except sqlite3.Error as e:
        logger.warning("failed to update permissions for %s: %s", sub, e)


def has_admin() -> bool:
    """Whether any known user is an admin (via login evaluation or a stored
    role override)."""
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE is_admin = 1 OR role_override = 'admin' LIMIT 1"
            ).fetchone()
            return row is not None
    except sqlite3.Error as e:
        logger.warning("failed to check for admins: %s", e)
        return False


def persist_session(session_id: str, sub: str) -> None:
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, sub, created_at) VALUES (?, ?, ?)",
                (session_id, sub, time.time()),
            )
    except sqlite3.Error as e:
        logger.warning("failed to persist session: %s", e)


def load_session(session_id: str, ttl_seconds: float) -> dict[str, Any] | None:
    """Return the stored user for ``session_id`` plus the session's age, or
    None when unknown or expired (expired rows are deleted)."""
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                """
                SELECT s.created_at, u.sub, u.email, u.name, u.username,
                       u.groups_json, u.can_write, u.is_admin
                FROM sessions s JOIN users u ON u.sub = s.sub
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            age = time.time() - row[0]
            if age > ttl_seconds:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                return None
    except sqlite3.Error as e:
        logger.warning("failed to load session: %s", e)
        return None
    return {
        "age": max(age, 0.0),
        "sub": row[1],
        "email": row[2],
        "name": row[3],
        "username": row[4],
        "groups": tuple(json.loads(row[5] or "[]")),
        "can_write": bool(row[6]),
        "is_admin": bool(row[7]),
    }


def delete_session(session_id: str) -> None:
    try:
        with _lock, _connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    except sqlite3.Error as e:
        logger.warning("failed to delete session: %s", e)


def delete_sessions_for_sub(sub: str) -> list[str]:
    try:
        with _lock, _connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE sub = ?", (sub,)
            ).fetchall()
            conn.execute("DELETE FROM sessions WHERE sub = ?", (sub,))
            return [r[0] for r in rows]
    except sqlite3.Error as e:
        logger.warning("failed to delete sessions for %s: %s", sub, e)
        return []


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _api_token_row(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "hint": row[2],
        "created_at": row[3],
        "last_used_at": row[4],
    }


def create_api_token(sub: str, name: str) -> tuple[str, dict[str, Any]] | None:
    """Mint a personal API token for ``sub``. Returns the plaintext token
    (shown to the user once; only its hash is stored) and its metadata, or
    None on a database error."""
    token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_id = secrets.token_hex(8)
    hint = token[-4:]
    now = _now_iso()
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO api_tokens (id, sub, name, token_hash, hint, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token_id, sub, name, hash_api_token(token), hint, now),
            )
    except sqlite3.Error as e:
        logger.warning("failed to create API token for %s: %s", sub, e)
        return None
    return token, _api_token_row((token_id, name, hint, now, None))


def list_api_tokens(sub: str) -> list[dict[str, Any]]:
    try:
        with _lock, _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, hint, created_at, last_used_at
                FROM api_tokens WHERE sub = ? ORDER BY created_at DESC
                """,
                (sub,),
            ).fetchall()
    except sqlite3.Error as e:
        logger.warning("failed to list API tokens for %s: %s", sub, e)
        return []
    return [_api_token_row(row) for row in rows]


def delete_api_token(sub: str, token_id: str) -> bool:
    try:
        with _lock, _connect() as conn:
            cursor = conn.execute(
                "DELETE FROM api_tokens WHERE id = ? AND sub = ?", (token_id, sub)
            )
            _api_token_cache.clear()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.warning("failed to delete API token %s: %s", token_id, e)
        return False


def delete_api_tokens_for_sub(sub: str) -> int:
    try:
        with _lock, _connect() as conn:
            cursor = conn.execute("DELETE FROM api_tokens WHERE sub = ?", (sub,))
            _api_token_cache.clear()
            return cursor.rowcount
    except sqlite3.Error as e:
        logger.warning("failed to delete API tokens for %s: %s", sub, e)
        return 0


def resolve_api_token(token: str) -> dict[str, Any] | None:
    """Return the user owning a personal API token, with permissions read
    from the users table, or None when the token is unknown or revoked.
    Lookups are cached briefly since this runs on the request path; revoking
    a token or changing a user's permissions clears the cache."""
    token_hash = hash_api_token(token)
    now = time.monotonic()
    with _lock:
        cached = _api_token_cache.get(token_hash)
    if cached is not None and now - cached[1] < _API_TOKEN_CACHE_TTL:
        return cached[0]
    user: dict[str, Any] | None = None
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                """
                SELECT t.id, u.sub, u.email, u.name, u.username,
                       u.can_write, u.is_admin
                FROM api_tokens t JOIN users u ON u.sub = t.sub
                WHERE t.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is not None:
                user = {
                    "token_id": row[0],
                    "sub": row[1],
                    "email": row[2],
                    "name": row[3],
                    "username": row[4],
                    "can_write": bool(row[5]),
                    "is_admin": bool(row[6]),
                }
                last_touch = _api_token_last_touch.get(row[0])
                if last_touch is None or now - last_touch > _API_TOKEN_TOUCH_INTERVAL:
                    _api_token_last_touch[row[0]] = now
                    conn.execute(
                        "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                        (_now_iso(), row[0]),
                    )
    except sqlite3.Error as e:
        logger.warning("failed to resolve API token: %s", e)
        return None
    with _lock:
        _api_token_cache[token_hash] = (user, now)
    return user


def record_activity(actor: str, project: str, action: str) -> None:
    """Upsert an (actor, project, action) counter. High-frequency actions
    (per-step logging) are throttled to one database write per minute per
    key; the count still increments on every flushed write batch."""
    key = (actor, project, action)
    now_monotonic = time.monotonic()
    with _lock:
        last = _last_activity_write.get(key)
        if last is not None and now_monotonic - last < _ACTIVITY_THROTTLE_SECONDS:
            return
        _last_activity_write[key] = now_monotonic
    now = _now_iso()
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO actor_projects (actor, project, action, count, first_seen, last_seen)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(actor, project, action) DO UPDATE SET
                    count=count + 1,
                    last_seen=excluded.last_seen
                """,
                (actor, project, action, now, now),
            )
    except sqlite3.Error as e:
        logger.warning("failed to record activity: %s", e)


def list_users() -> list[dict[str, Any]]:
    try:
        with _lock, _connect() as conn:
            user_rows = conn.execute(
                """
                SELECT sub, email, name, username, groups_json, can_write,
                       is_admin, first_login, last_login, login_count,
                       role_override
                FROM users ORDER BY last_login DESC
                """
            ).fetchall()
            session_counts = dict(
                conn.execute(
                    "SELECT sub, COUNT(*) FROM sessions GROUP BY sub"
                ).fetchall()
            )
            token_counts = dict(
                conn.execute(
                    "SELECT sub, COUNT(*) FROM api_tokens GROUP BY sub"
                ).fetchall()
            )
            project_rows = conn.execute(
                """
                SELECT actor, project, action, count, first_seen, last_seen
                FROM actor_projects ORDER BY last_seen DESC
                """
            ).fetchall()
    except sqlite3.Error as e:
        logger.warning("failed to list users: %s", e)
        return []

    projects_by_actor: dict[str, dict[str, dict[str, Any]]] = {}
    for actor, project, action, count, first_seen, last_seen in project_rows:
        entry = projects_by_actor.setdefault(actor, {}).setdefault(
            project,
            {
                "project": project,
                "actions": {},
                "first_seen": first_seen,
                "last_seen": last_seen,
            },
        )
        entry["actions"][action] = count
        if first_seen and (
            entry["first_seen"] is None or first_seen < entry["first_seen"]
        ):
            entry["first_seen"] = first_seen
        if last_seen and (entry["last_seen"] is None or last_seen > entry["last_seen"]):
            entry["last_seen"] = last_seen

    users = []
    for row in user_rows:
        sub = row[0]
        users.append(
            {
                "sub": sub,
                "email": row[1],
                "name": row[2],
                "username": row[3],
                "groups": json.loads(row[4] or "[]"),
                "can_write": bool(row[5]),
                "is_admin": bool(row[6]),
                "first_login": row[7],
                "last_login": row[8],
                "login_count": row[9],
                "role_override": row[10],
                "auth_type": "local" if is_local_sub(sub) else "oidc",
                "active_sessions": session_counts.get(sub, 0),
                "api_tokens": token_counts.get(sub, 0),
                "projects": sorted(
                    projects_by_actor.get(sub, {}).values(),
                    key=lambda p: p["last_seen"] or "",
                    reverse=True,
                ),
            }
        )
    return users


def write_token_projects() -> list[dict[str, Any]]:
    """Projects written by clients authenticating with the write token."""
    try:
        with _lock, _connect() as conn:
            rows = conn.execute(
                """
                SELECT project, action, count, first_seen, last_seen
                FROM actor_projects WHERE actor = ? ORDER BY last_seen DESC
                """,
                (WRITE_TOKEN_ACTOR,),
            ).fetchall()
    except sqlite3.Error as e:
        logger.warning("failed to list write-token projects: %s", e)
        return []
    by_project: dict[str, dict[str, Any]] = {}
    for project, action, count, first_seen, last_seen in rows:
        entry = by_project.setdefault(
            project,
            {
                "project": project,
                "actions": {},
                "first_seen": first_seen,
                "last_seen": last_seen,
            },
        )
        entry["actions"][action] = count
        if first_seen and (
            entry["first_seen"] is None or first_seen < entry["first_seen"]
        ):
            entry["first_seen"] = first_seen
        if last_seen and (entry["last_seen"] is None or last_seen > entry["last_seen"]):
            entry["last_seen"] = last_seen
    return sorted(by_project.values(), key=lambda p: p["last_seen"] or "", reverse=True)
