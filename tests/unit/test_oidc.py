"""Tests for generic OIDC authentication."""

import time
from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trackio import oidc


@pytest.fixture(autouse=True)
def clean_oidc_state(monkeypatch):
    for var in (
        "TRACKIO_OIDC_ISSUER",
        "TRACKIO_OIDC_CLIENT_ID",
        "TRACKIO_OIDC_CLIENT_SECRET",
        "TRACKIO_OIDC_SCOPES",
        "TRACKIO_OIDC_ALLOWED_USERS",
        "TRACKIO_OIDC_ALLOWED_GROUPS",
        "TRACKIO_OIDC_WRITE_USERS",
        "TRACKIO_OIDC_WRITE_GROUPS",
        "TRACKIO_OIDC_GROUPS_CLAIM",
        "TRACKIO_AUTH_REQUIRED",
        "TRACKIO_OIDC_COOKIE_SECURE",
    ):
        monkeypatch.delenv(var, raising=False)
    oidc._sessions.clear()
    oidc._pending_states.clear()
    yield
    oidc._sessions.clear()
    oidc._pending_states.clear()


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
    assert not config.auth_required


def test_auth_required_flag(monkeypatch):
    _configure(monkeypatch, TRACKIO_AUTH_REQUIRED="1")
    assert oidc.auth_required()


def test_permissions_default_all_can_write(monkeypatch):
    config = _configure(monkeypatch)
    allowed, can_write = oidc.evaluate_permissions(
        config, {"sub": "abc", "email": "a@b.c"}
    )
    assert allowed and can_write


def test_permissions_allowed_users(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_USERS="a@b.c, other@x.y")
    allowed, _ = oidc.evaluate_permissions(config, {"sub": "s", "email": "A@B.C"})
    assert allowed
    allowed, can_write = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "nope@b.c"}
    )
    assert not allowed and not can_write


def test_permissions_allowed_groups(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_ALLOWED_GROUPS="ml-team")
    allowed, _ = oidc.evaluate_permissions(
        config, {"sub": "s", "groups": ["ml-team", "misc"]}
    )
    assert allowed
    allowed, _ = oidc.evaluate_permissions(config, {"sub": "s", "groups": ["misc"]})
    assert not allowed


def test_permissions_write_users(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_WRITE_USERS="admin@b.c")
    allowed, can_write = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "admin@b.c"}
    )
    assert allowed and can_write
    allowed, can_write = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "viewer@b.c"}
    )
    assert allowed and not can_write


def test_permissions_write_star(monkeypatch):
    config = _configure(monkeypatch, TRACKIO_OIDC_WRITE_USERS="*")
    _, can_write = oidc.evaluate_permissions(config, {"sub": "s"})
    assert can_write


def test_permissions_write_groups(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_WRITE_USERS="admin@b.c",
        TRACKIO_OIDC_WRITE_GROUPS="trackio-writers",
    )
    _, can_write = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "u@b.c", "groups": ["trackio-writers"]}
    )
    assert can_write
    _, can_write = oidc.evaluate_permissions(
        config, {"sub": "s", "email": "u@b.c", "groups": ["readers"]}
    )
    assert not can_write


def test_permissions_custom_groups_claim(monkeypatch):
    config = _configure(
        monkeypatch,
        TRACKIO_OIDC_GROUPS_CLAIM="roles",
        TRACKIO_OIDC_WRITE_GROUPS="writer",
    )
    _, can_write = oidc.evaluate_permissions(config, {"sub": "s", "roles": ["writer"]})
    assert can_write


def _mock_request_with_cookie(cookie: str) -> Mock:
    request = Mock()
    request.headers = {"cookie": cookie}
    return request


def _install_session(session_id: str = "sess123", can_write: bool = True):
    oidc._sessions[session_id] = oidc.OidcSession(
        sub="user-1",
        email="a@b.c",
        name="Alice",
        username="alice",
        groups=("ml-team",),
        can_write=can_write,
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
    assert resp.headers["location"].endswith(oidc.OIDC_START_PATH)
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
