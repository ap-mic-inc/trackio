"""Tests for generic OIDC authentication, the auth store, and admin APIs."""

import time
from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trackio import auth_store, oidc


@pytest.fixture(autouse=True)
def clean_oidc_state(monkeypatch, tmp_path):
    for var in (
        "TRACKIO_OIDC_ISSUER",
        "TRACKIO_OIDC_CLIENT_ID",
        "TRACKIO_OIDC_CLIENT_SECRET",
        "TRACKIO_OIDC_SCOPES",
        "TRACKIO_OIDC_ALLOWED_USERS",
        "TRACKIO_OIDC_ALLOWED_GROUPS",
        "TRACKIO_OIDC_WRITE_USERS",
        "TRACKIO_OIDC_WRITE_GROUPS",
        "TRACKIO_OIDC_ADMIN_USERS",
        "TRACKIO_OIDC_ADMIN_GROUPS",
        "TRACKIO_OIDC_GROUPS_CLAIM",
        "TRACKIO_AUTH_REQUIRED",
        "TRACKIO_OIDC_COOKIE_SECURE",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("trackio.utils.TRACKIO_DIR", tmp_path)
    oidc._sessions.clear()
    oidc._pending_states.clear()
    auth_store._last_activity_write.clear()
    auth_store._settings_cache.clear()
    yield
    oidc._sessions.clear()
    oidc._pending_states.clear()
    auth_store._last_activity_write.clear()
    auth_store._settings_cache.clear()


def _configure(monkeypatch, **env):
    monkeypatch.setenv("TRACKIO_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("TRACKIO_OIDC_CLIENT_ID", "trackio")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return oidc.load_oidc_config()


def test_disabled_without_issuer():
    assert oidc.load_oidc_config() is None
    assert not oidc.oidc_enabled()
    assert not oidc.auth_required()


def test_disabled_without_client_id(monkeypatch):
    monkeypatch.setenv("TRACKIO_OIDC_ISSUER", "https://idp.example.com")
    assert oidc.load_oidc_config() is None


def test_config_defaults(monkeypatch):
    config = _configure(monkeypatch)
    assert config.issuer == "https://idp.example.com"
    assert config.scopes == "openid profile email"
    assert config.groups_claim == "groups"
    assert config.write_open_to_all


def test_auth_required_flag(monkeypatch):
    _configure(monkeypatch, TRACKIO_AUTH_REQUIRED="1")
    assert oidc.auth_required()


def test_permissions_default_all_can_write(monkeypatch):
    config = _configure(monkeypatch)
    allowed, can_write, is_admin = oidc.evaluate_permissions(
        config, {"sub": "abc", "email": "a@b.c"}
    )
    assert allowed and can_write and not is_admin


def test_permissions_allowed_users(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_USERS="a@b.c, other@x.y")
    allowed, _, _ = oidc.evaluate_permissions(config, {"sub": "s", "email": "A@B.C"})
    assert allowed
    allowed, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "nope@b.c"}
    )
    assert not allowed and not can_write


def test_permissions_allowed_groups(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_GROUPS="ml-team")
    allowed, _, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "groups": ["ml-team", "misc"]}
    )
    assert allowed
    allowed, _, _ = oidc.evaluate_permissions(config, {"sub": "s", "groups": ["misc"]})
    assert not allowed


def test_permissions_write_users(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_WRITE_USERS="admin@b.c")
    allowed, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "admin@b.c"}
    )
    assert allowed and can_write
    allowed, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "viewer@b.c"}
    )
    assert allowed and not can_write


def test_permissions_write_star(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_WRITE_USERS="*")
    _, can_write, _ = oidc.evaluate_permissions(config, {"sub": "s"})
    assert can_write


def test_permissions_write_groups(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_WRITE_USERS="admin@b.c",
        TRACKIO_OIDC_WRITE_GROUPS="trackio-writers",
    )
    _, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "u@b.c", "groups": ["trackio-writers"]}
    )
    assert can_write
    _, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "u@b.c", "groups": ["readers"]}
    )
    assert not can_write


def test_permissions_custom_groups_claim(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_GROUPS_CLAIM="roles",
        TRACKIO_OIDC_WRITE_GROUPS="writer",
    )
    _, can_write, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "roles": ["writer"]}
    )
    assert can_write


def test_permissions_admin_users(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_WRITE_USERS="writer@b.c",
        TRACKIO_OIDC_ADMIN_USERS="boss@b.c",
    )
    allowed, can_write, is_admin = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "boss@b.c"}
    )
    assert allowed and can_write and is_admin
    allowed, can_write, is_admin = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "writer@b.c"}
    )
    assert allowed and can_write and not is_admin


def test_permissions_admin_bypasses_allowed_list(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_ALLOWED_USERS="member@b.c",
        TRACKIO_OIDC_ADMIN_GROUPS="ops",
    )
    allowed, can_write, is_admin = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "boss@b.c", "groups": ["ops"]}
    )
    assert allowed and can_write and is_admin
    allowed, _, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "random@b.c"}
    )
    assert not allowed


def _mock_request_with_cookie(cookie: str) -> Mock:
    request = Mock()
    request.headers = {"cookie": cookie}
    return request


def _install_session(
    session_id: str = "sess123",
    can_write: bool = True,
    is_admin: bool = False,
    sub: str = "user-1",
    name: str = "Alice",
):
    oidc._sessions[session_id] = oidc.OidcSession(
        sub=sub,
        email="a@b.c",
        name=name,
        username="alice",
        groups=("ml-team",),
        can_write=can_write,
        is_admin=is_admin,
    )
    return session_id


def test_get_oidc_session_roundtrip():
    session_id = _install_session()
    request = _mock_request_with_cookie(f"trackio_oidc_session={session_id}")
    session = oidc.get_oidc_session(request)
    assert session is not None
    assert session.display_name == "Alice"

    request = _mock_request_with_cookie("trackio_oidc_session=unknown")
    assert oidc.get_oidc_session(request) is None

    request = _mock_request_with_cookie("")
    assert oidc.get_oidc_session(request) is None


def test_get_oidc_session_expired():
    session_id = _install_session()
    oidc._sessions[session_id].created = time.monotonic() - oidc._SESSION_TTL - 1
    request = _mock_request_with_cookie(f"trackio_oidc_session={session_id}")
    assert oidc.get_oidc_session(request) is None
    assert session_id not in oidc._sessions


def test_session_survives_restart():
    auth_store.record_login(
        sub="user-1",
        email="a@b.c",
        name="Alice",
        username="alice",
        groups=("ml-team",),
        can_write=True,
        is_admin=True,
    )
    auth_store.persist_session("persisted-1", "user-1")

    oidc._sessions.clear()
    request = _mock_request_with_cookie("trackio_oidc_session=persisted-1")
    session = oidc.get_oidc_session(request)
    assert session is not None
    assert session.sub == "user-1"
    assert session.can_write and session.is_admin
    assert "persisted-1" in oidc._sessions


def test_revoke_sessions_for_sub():
    _install_session("s1", sub="user-1")
    _install_session("s2", sub="user-1")
    _install_session("s3", sub="user-2", name="Bob")
    auth_store.record_login("user-1", "a@b.c", "Alice", "alice", (), True, False)
    auth_store.persist_session("s1", "user-1")
    auth_store.persist_session("s2", "user-1")

    revoked = oidc.revoke_sessions_for_sub("user-1")
    assert revoked == 2
    assert "s1" not in oidc._sessions and "s2" not in oidc._sessions
    assert "s3" in oidc._sessions
    request = _mock_request_with_cookie("trackio_oidc_session=s1")
    assert oidc.get_oidc_session(request) is None


def test_auth_store_login_and_users():
    auth_store.record_login("u1", "a@b.c", "Alice", "alice", ("ml",), True, False)
    auth_store.record_login("u1", "a@b.c", "Alice", "alice", ("ml",), True, True)
    auth_store.record_login("u2", "b@b.c", "Bob", "bob", (), False, False)
    auth_store.persist_session("sess-a", "u1")

    users = auth_store.list_users()
    by_sub = {u["sub"]: u for u in users}
    assert by_sub["u1"]["login_count"] == 2
    assert by_sub["u1"]["is_admin"] is True
    assert by_sub["u1"]["active_sessions"] == 1
    assert by_sub["u2"]["can_write"] is False
    assert by_sub["u2"]["active_sessions"] == 0


def test_auth_store_activity_and_throttle():
    auth_store.record_activity("u1", "proj-a", "log")
    auth_store.record_activity("u1", "proj-a", "log")
    users = auth_store.list_users()
    auth_store.record_login("u1", "a@b.c", "Alice", "alice", (), True, False)
    users = auth_store.list_users()
    projects = users[0]["projects"]
    assert len(projects) == 1
    assert projects[0]["project"] == "proj-a"
    assert projects[0]["actions"] == {"log": 1}

    auth_store._last_activity_write.clear()
    auth_store.record_activity("u1", "proj-a", "log")
    auth_store.record_activity("u1", "proj-b", "manage")
    users = auth_store.list_users()
    projects = {p["project"]: p for p in users[0]["projects"]}
    assert projects["proj-a"]["actions"] == {"log": 2}
    assert projects["proj-b"]["actions"] == {"manage": 1}


def test_auth_store_write_token_projects():
    auth_store.record_activity(auth_store.WRITE_TOKEN_ACTOR, "proj-x", "log")
    entries = auth_store.write_token_projects()
    assert len(entries) == 1
    assert entries[0]["project"] == "proj-x"
    assert entries[0]["actions"] == {"log": 1}


def test_auth_store_session_expiry():
    auth_store.record_login("u1", "a@b.c", "Alice", "alice", (), True, False)
    auth_store.persist_session("old", "u1")
    assert auth_store.load_session("old", ttl_seconds=0) is None
    assert auth_store.load_session("old", ttl_seconds=3600) is None


def test_server_write_checks_accept_oidc(monkeypatch):
    from trackio import server

    _configure(monkeypatch)
    session_id = _install_session(can_write=True)
    request = _mock_request_with_cookie(f"trackio_oidc_session={session_id}")
    request.query_params = {}
    server.assert_can_write_metrics(request, hf_token=None)
    server.assert_can_stage_upload(request)
    server.assert_can_mutate_runs(request)

    readonly_id = _install_session(session_id="readonly", can_write=False)
    request = _mock_request_with_cookie(f"trackio_oidc_session={readonly_id}")
    request.query_params = {}
    from trackio.exceptions import TrackioAPIError

    with pytest.raises(TrackioAPIError):
        server.assert_can_write_metrics(request, hf_token=None)
    with pytest.raises(TrackioAPIError):
        server.assert_can_mutate_runs(request)


def test_get_run_mutation_status_reports_oidc(monkeypatch):
    from trackio import server

    _configure(monkeypatch)
    session_id = _install_session(can_write=True)
    request = _mock_request_with_cookie(f"trackio_oidc_session={session_id}")
    request.query_params = {}
    status = server.get_run_mutation_status(request)
    assert status["allowed"] is True
    assert status["auth"] == "oidc"
    assert status["oidc_enabled"] is True
    assert status["user"] == "Alice"
    assert status["admin"] is False

    admin_id = _install_session(session_id="adm", is_admin=True, name="Root")
    request = _mock_request_with_cookie(f"trackio_oidc_session={admin_id}")
    request.query_params = {}
    status = server.get_run_mutation_status(request)
    assert status["admin"] is True

    readonly_id = _install_session(session_id="readonly", can_write=False)
    request = _mock_request_with_cookie(f"trackio_oidc_session={readonly_id}")
    request.query_params = {}
    status = server.get_run_mutation_status(request)
    assert status["allowed"] is False
    assert status["auth"] == "oidc_insufficient"

    request = _mock_request_with_cookie("")
    request.query_params = {}
    status = server.get_run_mutation_status(request)
    assert status["auth"] == "none"
    assert status["oidc_enabled"] is True
    assert status["user"] is None
    assert status["admin"] is False


def test_admin_endpoints(monkeypatch):
    from trackio import server
    from trackio.exceptions import TrackioAPIError

    _configure(monkeypatch)
    auth_store.record_login("user-1", "a@b.c", "Alice", "alice", (), True, False)
    auth_store.persist_session("sess123", "user-1")
    auth_store.record_activity("user-1", "proj-a", "log")

    viewer_id = _install_session(
        session_id="viewer", can_write=False, sub="user-viewer"
    )
    request = _mock_request_with_cookie(f"trackio_oidc_session={viewer_id}")
    request.query_params = {}
    with pytest.raises(TrackioAPIError):
        server.admin_get_users(request)

    admin_id = _install_session(
        session_id="adm", is_admin=True, sub="user-admin", name="Root"
    )
    request = _mock_request_with_cookie(f"trackio_oidc_session={admin_id}")
    request.query_params = {}
    result = server.admin_get_users(request)
    assert result["oidc_enabled"] is True
    subs = [u["sub"] for u in result["users"]]
    assert "user-1" in subs
    user = next(u for u in result["users"] if u["sub"] == "user-1")
    assert user["projects"][0]["project"] == "proj-a"
    assert user["active_sessions"] == 1

    token_request = Mock()
    token_request.headers = {"x-trackio-write-token": server.write_token}
    token_request.query_params = {}
    result = server.admin_get_users(token_request)
    assert "user-1" in [u["sub"] for u in result["users"]]

    _install_session("sess123", sub="user-1")
    revoke = server.admin_revoke_user_sessions(request, "user-1")
    assert revoke["revoked"] == 1
    result = server.admin_get_users(request)
    user = next(u for u in result["users"] if u["sub"] == "user-1")
    assert user["active_sessions"] == 0


def _make_gated_app(write_token: str = "wt-secret") -> TestClient:
    async def api_endpoint(request):
        return JSONResponse({"data": "ok"})

    async def index(request):
        return JSONResponse({"page": "index"})

    app = Starlette(
        routes=[
            Route("/api/get_all_projects", api_endpoint, methods=["POST"]),
            Route("/version", index, methods=["GET"]),
            Route("/", index, methods=["GET"]),
        ]
    )
    app.add_middleware(
        oidc.OidcAuthRequiredMiddleware,
        write_token_checker=lambda req: (
            req.headers.get("x-trackio-write-token") == write_token
        ),
    )
    return TestClient(app, follow_redirects=False)


def test_middleware_noop_when_auth_not_required(monkeypatch):
    _configure(monkeypatch)
    client = _make_gated_app()
    assert client.post("/api/get_all_projects").status_code == 200
    assert client.get("/").status_code == 200


def test_middleware_blocks_without_session(monkeypatch):
    _configure(monkeypatch, TRACKIO_AUTH_REQUIRED="1")
    client = _make_gated_app()
    resp = client.post("/api/get_all_projects")
    assert resp.status_code == 401
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/login")
    assert client.get("/version").status_code == 200


def test_middleware_allows_session_and_write_token(monkeypatch):
    _configure(monkeypatch, TRACKIO_AUTH_REQUIRED="1")
    session_id = _install_session()
    client = _make_gated_app()
    resp = client.post(
        "/api/get_all_projects",
        headers={"cookie": f"trackio_oidc_session={session_id}"},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/get_all_projects",
        headers={"x-trackio-write-token": "wt-secret"},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/get_all_projects",
        headers={"x-trackio-write-token": "wrong"},
    )
    assert resp.status_code == 401


def test_jwt_claims_decoding():
    import base64
    import json

    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "abc", "email": "a@b.c"}).encode())
        .decode()
        .rstrip("=")
    )
    token = f"header.{payload}.signature"
    claims = oidc._decode_jwt_claims(token)
    assert claims == {"sub": "abc", "email": "a@b.c"}
    assert oidc._decode_jwt_claims("garbage") == {}


def test_apply_role_override():
    assert oidc.apply_role_override(False, False, "admin") == (True, True)
    assert oidc.apply_role_override(False, False, "write") == (True, False)
    assert oidc.apply_role_override(True, True, "read") == (False, False)
    assert oidc.apply_role_override(True, False, None) == (True, False)


def test_resolve_login_denies_disallowed_user(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_USERS="member@b.c")
    allowed, can_write, is_admin = oidc.resolve_login_permissions(
        config, {"sub": "s", "email": "random@b.c"}
    )
    assert not allowed and not can_write and not is_admin


def test_role_override_wins_over_env(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_WRITE_USERS="writer@b.c")
    auth_store.set_role_override("demoted", None)
    auth_store.set_role_override("promoted", "admin")
    auth_store.set_role_override("readonly", "read")

    allowed, can_write, is_admin = oidc.resolve_login_permissions(
        config, {"sub": "promoted", "email": "nobody@b.c"}
    )
    assert allowed and can_write and is_admin

    allowed, can_write, _ = oidc.resolve_login_permissions(
        config, {"sub": "readonly", "email": "writer@b.c"}
    )
    assert allowed and not can_write


def test_override_allows_signin_despite_allowed_list(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_USERS="member@b.c")
    auth_store.set_role_override("outsider", "write")
    allowed, can_write, _ = oidc.resolve_login_permissions(
        config, {"sub": "outsider", "email": "outsider@b.c"}
    )
    assert allowed and can_write


def test_refresh_user_permissions_updates_live_sessions(monkeypatch):
    _configure(monkeypatch)
    auth_store.record_login("user-1", "a@b.c", "Alice", "alice", (), True, False)
    session_id = _install_session(can_write=True, is_admin=False)

    auth_store.set_role_override("user-1", "read")
    permissions = oidc.refresh_user_permissions("user-1")
    assert permissions == {"can_write": False, "is_admin": False}
    assert oidc._sessions[session_id].can_write is False

    auth_store.set_role_override("user-1", "admin")
    permissions = oidc.refresh_user_permissions("user-1")
    assert permissions == {"can_write": True, "is_admin": True}
    assert oidc._sessions[session_id].is_admin is True

    assert oidc.refresh_user_permissions("ghost") is None


def test_admin_set_role_endpoint(monkeypatch):
    from trackio import server
    from trackio.exceptions import TrackioAPIError

    _configure(monkeypatch)
    auth_store.record_login("user-v", "v@b.c", "Viewer", "v", (), False, False)
    viewer_id = _install_session(
        session_id="viewer", can_write=False, sub="user-v", name="Viewer"
    )
    admin_id = _install_session(
        session_id="adm", is_admin=True, sub="user-a", name="Root"
    )
    request = _mock_request_with_cookie(f"trackio_oidc_session={admin_id}")
    request.query_params = {}

    result = server.admin_set_role(request, "user-v", "admin")
    assert result["is_admin"] is True
    assert oidc._sessions[viewer_id].is_admin is True

    result = server.admin_set_role(request, "user-v", "read")
    assert result["can_write"] is False
    assert oidc._sessions[viewer_id].can_write is False

    result = server.admin_set_role(request, "user-v", "default")
    users = {u["sub"]: u for u in auth_store.list_users()}
    assert users["user-v"]["role_override"] is None

    with pytest.raises(TrackioAPIError):
        server.admin_set_role(request, "user-v", "superuser")
    with pytest.raises(TrackioAPIError):
        server.admin_set_role(request, "ghost", "admin")

    viewer_request = _mock_request_with_cookie(f"trackio_oidc_session={viewer_id}")
    viewer_request.query_params = {}
    with pytest.raises(TrackioAPIError):
        server.admin_set_role(viewer_request, "user-v", "admin")


def test_db_settings_take_precedence_over_env(monkeypatch):
    _configure(monkeypatch)
    assert oidc.load_oidc_config() is not None

    auth_store.set_setting(
        oidc.AUTH_SETTINGS_KEY,
        {
            "issuer": "https://db-idp.example.com/",
            "client_id": "db-client",
            "client_secret": "db-secret",
            "write_users": "w@b.c",
        },
    )
    config = oidc.load_oidc_config()
    assert config is not None
    assert config.issuer == "https://db-idp.example.com"
    assert config.client_id == "db-client"
    assert "w@b.c" in config.write_users
    assert not config.write_open_to_all


def test_env_fallback_when_db_settings_lack_issuer(monkeypatch):
    _configure(monkeypatch)
    auth_store.set_setting(oidc.AUTH_SETTINGS_KEY, {"auth_required": True})
    config = oidc.load_oidc_config()
    assert config is not None
    assert config.issuer == "https://idp.example.com"


def test_saved_config_enables_oidc_without_legacy_flag():
    auth_store.set_setting(
        oidc.AUTH_SETTINGS_KEY,
        {
            "oidc_enabled": False,
            "issuer": "https://db-idp.example.com",
            "client_id": "db-client",
        },
    )
    assert oidc.oidc_enabled()


def test_db_settings_require_issuer_and_client():
    auth_store.set_setting(oidc.AUTH_SETTINGS_KEY, {"issuer": "", "client_id": "x"})
    assert oidc.load_oidc_config() is None
    auth_store.set_setting(
        oidc.AUTH_SETTINGS_KEY,
        {"issuer": "https://x", "client_id": ""},
    )
    assert oidc.load_oidc_config() is None


def test_auth_required_from_db_setting():
    assert not oidc.auth_required()
    auth_store.set_setting(oidc.AUTH_SETTINGS_KEY, {"auth_required": True})
    assert oidc.auth_required()
    auth_store.set_setting(oidc.AUTH_SETTINGS_KEY, {"auth_required": False})
    assert not oidc.auth_required()


def test_admin_auth_settings_api():
    from trackio import server
    from trackio.exceptions import TrackioAPIError

    admin_id = _install_session(session_id="adm", is_admin=True, sub="user-a")
    request = _mock_request_with_cookie(f"trackio_oidc_session={admin_id}")
    request.query_params = {}

    payload = server.admin_get_auth_settings(request)
    assert payload["source"] == "env"
    assert payload["oidc_active"] is False

    with pytest.raises(TrackioAPIError):
        server.admin_set_auth_settings(
            request, {"issuer": "https://idp.example.com", "client_id": ""}
        )

    payload = server.admin_set_auth_settings(
        request,
        {
            "issuer": "https://idp.example.com",
            "client_id": "trackio",
            "client_secret": "topsecret",
            "auth_required": True,
        },
    )
    assert payload["source"] == "db"
    assert payload["oidc_active"] is True
    assert payload["auth_required_active"] is True
    assert payload["client_secret_set"] is True
    assert "client_secret" not in payload

    payload = server.admin_set_auth_settings(
        request,
        {
            "issuer": "https://idp.example.com",
            "client_id": "trackio",
            "client_secret": "",
        },
    )
    assert payload["client_secret_set"] is True
    config = oidc.load_oidc_config()
    assert config.client_secret == "topsecret"
    assert not oidc.auth_required()

    viewer_id = _install_session(session_id="viewer", can_write=False, sub="user-v")
    viewer_request = _mock_request_with_cookie(f"trackio_oidc_session={viewer_id}")
    viewer_request.query_params = {}
    with pytest.raises(TrackioAPIError):
        server.admin_get_auth_settings(viewer_request)
    with pytest.raises(TrackioAPIError):
        server.admin_test_oidc(viewer_request)


def test_admin_test_oidc_requires_issuer():
    from trackio import server
    from trackio.exceptions import TrackioAPIError

    admin_id = _install_session(session_id="adm", is_admin=True, sub="user-a")
    request = _mock_request_with_cookie(f"trackio_oidc_session={admin_id}")
    request.query_params = {}
    with pytest.raises(TrackioAPIError):
        server.admin_test_oidc(request)
