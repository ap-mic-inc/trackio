"""Tests for password-based local accounts and the first-run setup flow."""

from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from trackio import auth_store, local_auth, oidc


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    for var in (
        "TRACKIO_OIDC_ISSUER",
        "TRACKIO_OIDC_CLIENT_ID",
        "TRACKIO_OIDC_ADMIN_USERS",
        "TRACKIO_OIDC_ADMIN_GROUPS",
        "TRACKIO_AUTH_REQUIRED",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("trackio.utils.TRACKIO_DIR", tmp_path)
    oidc._sessions.clear()
    auth_store._settings_cache.clear()
    yield
    oidc._sessions.clear()
    auth_store._settings_cache.clear()


def _client() -> TestClient:
    app = Starlette(routes=local_auth.local_auth_routes())
    return TestClient(app, follow_redirects=False)


def _session_cookie(resp) -> str:
    cookie = resp.headers.get("set-cookie", "")
    assert oidc.OIDC_SESSION_COOKIE in cookie
    return cookie.split(";")[0]


def test_password_hash_roundtrip():
    stored = local_auth.hash_password("hunter2secret")
    assert stored.startswith("scrypt$")
    assert local_auth.verify_password("hunter2secret", stored)
    assert not local_auth.verify_password("wrong-password", stored)
    assert not local_auth.verify_password("hunter2secret", None)
    assert not local_auth.verify_password("hunter2secret", "garbage")
    assert local_auth.hash_password("hunter2secret") != stored


def test_validate_new_credentials():
    assert local_auth.validate_new_credentials("alice", "longenough") is None
    assert local_auth.validate_new_credentials("a", "longenough") is not None
    assert local_auth.validate_new_credentials("bad name", "longenough") is not None
    assert local_auth.validate_new_credentials("alice", "short") is not None


def test_setup_available_lifecycle(monkeypatch):
    assert local_auth.setup_available()

    sub, error = local_auth.create_local_account("root", "password123", "admin")
    assert error is None and sub == "local:root"
    assert not local_auth.setup_available()


def test_setup_disabled_with_env_admins(monkeypatch):
    monkeypatch.setenv("TRACKIO_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("TRACKIO_OIDC_CLIENT_ID", "trackio")
    monkeypatch.setenv("TRACKIO_OIDC_ADMIN_USERS", "boss@b.c")
    assert not local_auth.setup_available()


def test_create_local_account_roles_and_duplicates():
    sub, error = local_auth.create_local_account("writer", "password123", "write")
    assert error is None
    user = auth_store.get_user(sub)
    assert user["can_write"] and not user["is_admin"]

    sub, error = local_auth.create_local_account("reader", "password123", "read")
    user = auth_store.get_user(sub)
    assert not user["can_write"] and not user["is_admin"]

    _, error = local_auth.create_local_account("writer", "password123", "write")
    assert "already taken" in error
    _, error = local_auth.create_local_account("x2", "password123", "superuser")
    assert "role must be" in error


def test_setup_flow_end_to_end():
    client = _client()
    assert client.get("/setup").status_code == 200

    resp = client.post(
        "/setup",
        data={"username": "root", "password": "password123", "confirm": "different"},
    )
    assert resp.status_code == 200 and b"do not match" in resp.content

    resp = client.post(
        "/setup",
        data={"username": "root", "password": "password123", "confirm": "password123"},
    )
    assert resp.status_code == 302
    cookie = _session_cookie(resp)

    request = Mock()
    request.headers = {"cookie": cookie}
    session = oidc.get_oidc_session(request)
    assert session is not None
    assert session.is_admin and session.can_write
    assert session.sub == "local:root"

    resp = client.get("/setup")
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/login")
    resp = client.post(
        "/setup",
        data={"username": "evil", "password": "password123", "confirm": "password123"},
    )
    assert resp.status_code == 302
    assert auth_store.get_user("local:evil") is None


def test_login_flow():
    local_auth.create_local_account("alice", "password123", "write")
    client = _client()
    assert client.get("/login").status_code == 200

    resp = client.post(
        "/login", data={"username": "alice", "password": "wrong-password"}
    )
    assert resp.status_code == 200 and b"Invalid username or password" in resp.content

    resp = client.post("/login", data={"username": "ghost", "password": "password123"})
    assert resp.status_code == 200 and b"Invalid username or password" in resp.content

    resp = client.post("/login", data={"username": "alice", "password": "password123"})
    assert resp.status_code == 302
    cookie = _session_cookie(resp)
    request = Mock()
    request.headers = {"cookie": cookie}
    session = oidc.get_oidc_session(request)
    assert session is not None
    assert session.can_write and not session.is_admin
    assert session.display_name == "alice"


def test_admin_create_user_and_reset_password():
    from trackio import server
    from trackio.exceptions import TrackioAPIError

    local_auth.create_local_account("root", "password123", "admin")
    client = _client()
    resp = client.post("/login", data={"username": "root", "password": "password123"})
    admin_request = Mock()
    admin_request.headers = {"cookie": _session_cookie(resp)}
    admin_request.query_params = {}

    result = server.admin_create_user(
        admin_request, username="bob", password="password456", role="read"
    )
    assert result["sub"] == "local:bob"
    with pytest.raises(TrackioAPIError):
        server.admin_create_user(
            admin_request, username="bob", password="password456", role="read"
        )
    with pytest.raises(TrackioAPIError):
        server.admin_create_user(
            admin_request, username="carol", password="short", role="read"
        )

    server.admin_reset_password(admin_request, "local:bob", "newpassword789")
    resp = client.post("/login", data={"username": "bob", "password": "password456"})
    assert b"Invalid" in resp.content
    resp = client.post("/login", data={"username": "bob", "password": "newpassword789"})
    assert resp.status_code == 302

    with pytest.raises(TrackioAPIError):
        server.admin_reset_password(admin_request, "oidc-sub-123", "newpassword789")
    with pytest.raises(TrackioAPIError):
        server.admin_reset_password(admin_request, "local:ghost", "newpassword789")

    viewer_request = Mock()
    viewer_request.headers = {"cookie": ""}
    viewer_request.query_params = {}
    with pytest.raises(TrackioAPIError):
        server.admin_create_user(
            viewer_request, username="mallory", password="password456", role="admin"
        )
