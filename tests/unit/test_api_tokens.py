"""Tests for personal API tokens and per-user run attribution."""

import sqlite3
from unittest.mock import Mock

import pytest

from trackio import auth_store, oidc
from trackio.exceptions import TrackioAPIError


@pytest.fixture(autouse=True)
def clean_auth_state(monkeypatch, temp_dir):
    for var in ("TRACKIO_OIDC_ISSUER", "TRACKIO_AUTH_REQUIRED"):
        monkeypatch.delenv(var, raising=False)
    oidc._sessions.clear()
    auth_store._last_activity_write.clear()
    auth_store._settings_cache.clear()
    auth_store._api_token_cache.clear()
    auth_store._api_token_last_touch.clear()
    yield
    oidc._sessions.clear()
    auth_store._last_activity_write.clear()
    auth_store._api_token_cache.clear()
    auth_store._api_token_last_touch.clear()


def _user(sub="user-1", username="alice", can_write=True, is_admin=False):
    auth_store.record_login(
        sub,
        f"{username}@example.com",
        username.title(),
        username,
        (),
        can_write,
        is_admin,
    )
    return sub


def _session(sub="user-1", username="alice", can_write=True, is_admin=False):
    session_id = f"sess-{sub}"
    oidc._sessions[session_id] = oidc.OidcSession(
        sub=sub,
        email=f"{username}@example.com",
        name=username.title(),
        username=username,
        groups=(),
        can_write=can_write,
        is_admin=is_admin,
    )
    return session_id


def _request(headers=None, query=None):
    request = Mock()
    request.headers = headers or {}
    request.query_params = query or {}
    return request


def _token_request(token):
    return _request({"x-trackio-write-token": token})


def _session_request(session_id):
    return _request({"cookie": f"trackio_oidc_session={session_id}"})


def test_create_resolve_and_revoke_token():
    sub = _user()
    token, meta = auth_store.create_api_token(sub, "cluster")
    assert token.startswith(auth_store.API_TOKEN_PREFIX)
    assert meta["name"] == "cluster"
    assert meta["hint"] == token[-4:]

    with sqlite3.connect(auth_store._db_path()) as conn:
        stored = [row[0] for row in conn.execute("SELECT token_hash FROM api_tokens")]
    assert stored == [auth_store.hash_api_token(token)]
    assert token not in stored

    user = auth_store.resolve_api_token(token)
    assert user["sub"] == sub and user["can_write"] is True
    assert auth_store.list_api_tokens(sub)[0]["last_used_at"] is not None
    assert auth_store.resolve_api_token(token + "x") is None

    assert auth_store.delete_api_token("someone-else", meta["id"]) is False
    assert auth_store.delete_api_token(sub, meta["id"]) is True
    assert auth_store.resolve_api_token(token) is None
    assert auth_store.list_api_tokens(sub) == []


def test_token_follows_current_permissions():
    sub = _user()
    token, _ = auth_store.create_api_token(sub, "t")
    assert auth_store.resolve_api_token(token)["can_write"] is True
    auth_store.set_role_override(sub, "read")
    oidc.refresh_user_permissions(sub)
    assert auth_store.resolve_api_token(token)["can_write"] is False


def test_server_write_checks_accept_personal_token():
    from trackio import server

    sub = _user()
    token, _ = auth_store.create_api_token(sub, "t")
    request = _token_request(token)
    server.assert_can_write_metrics(request, hf_token=None)
    server.assert_can_stage_upload(request)
    server.assert_can_mutate_runs(request)
    assert not server._is_admin(request)
    with pytest.raises(TrackioAPIError):
        server.admin_get_users(request)

    with pytest.raises(TrackioAPIError):
        server.assert_can_write_metrics(_token_request("trk_unknown"), hf_token=None)

    query_request = _request(query={"write_token": token})
    server.assert_can_write_metrics(query_request, hf_token=None)


def test_read_only_and_revoked_tokens_cannot_write():
    from trackio import server

    reader = _user("user-r", "reader", can_write=False)
    token, _ = auth_store.create_api_token(reader, "t")
    with pytest.raises(TrackioAPIError):
        server.assert_can_write_metrics(_token_request(token), hf_token=None)

    writer = _user()
    token, _ = auth_store.create_api_token(writer, "t")
    server.assert_can_write_metrics(_token_request(token), hf_token=None)
    server.admin_revoke_user_tokens(_token_request(server.write_token), writer)
    with pytest.raises(TrackioAPIError):
        server.assert_can_write_metrics(_token_request(token), hf_token=None)


def test_write_activity_is_attributed_to_token_owner():
    from trackio import server

    sub = _user()
    token, _ = auth_store.create_api_token(sub, "t")
    server._record_write_activity(_token_request(token), "proj-a", "log")
    server._record_write_activity(_token_request(server.write_token), "proj-b", "log")

    users = {u["sub"]: u for u in auth_store.list_users()}
    assert [p["project"] for p in users[sub]["projects"]] == ["proj-a"]
    assert users[sub]["api_tokens"] == 1
    assert [p["project"] for p in auth_store.write_token_projects()] == ["proj-b"]


def test_bulk_log_records_verified_username():
    from trackio import server
    from trackio.sqlite_storage import SQLiteStorage

    sub = _user()
    token, _ = auth_store.create_api_token(sub, "t")
    server.bulk_log(
        _token_request(token),
        [
            {
                "project": "attrib",
                "run": "run-token",
                "run_id": "rid-token",
                "metrics": {"loss": 1.0},
                "step": 0,
                "config": {"lr": 0.1, "_Username": "spoofed"},
            }
        ],
        hf_token=None,
    )
    server.bulk_log(
        _token_request(server.write_token),
        [
            {
                "project": "attrib",
                "run": "run-shared",
                "run_id": "rid-shared",
                "metrics": {"loss": 1.0},
                "step": 0,
                "config": {"lr": 0.1, "_Username": "client-side"},
            }
        ],
        hf_token=None,
    )
    token_config = SQLiteStorage.get_run_config(
        "attrib", "run-token", run_id="rid-token"
    )
    shared_config = SQLiteStorage.get_run_config(
        "attrib", "run-shared", run_id="rid-shared"
    )
    assert token_config["_Username"] == "alice"
    assert token_config["lr"] == 0.1
    assert shared_config["_Username"] == "client-side"


def test_self_service_token_api_requires_session():
    from trackio import server

    sub = _user()
    session_request = _session_request(_session(sub))

    created = server.create_my_api_token(session_request, "  laptop ")
    assert created["name"] == "laptop"
    assert created["token"].startswith(auth_store.API_TOKEN_PREFIX)

    listed = server.get_my_api_tokens(session_request)
    assert [t["id"] for t in listed["tokens"]] == [created["id"]]
    assert "token" not in listed["tokens"][0]
    assert listed["can_write"] is True

    with pytest.raises(TrackioAPIError):
        server.create_my_api_token(_token_request(created["token"]), "minted")
    with pytest.raises(TrackioAPIError):
        server.get_my_api_tokens(_token_request(server.write_token))
    with pytest.raises(TrackioAPIError):
        server.create_my_api_token(session_request, "x" * 65)

    other_request = _session_request(_session("user-2", "bob"))
    with pytest.raises(TrackioAPIError):
        server.revoke_my_api_token(other_request, created["id"])

    server.revoke_my_api_token(session_request, created["id"])
    assert server.get_my_api_tokens(session_request)["tokens"] == []


def test_mutation_status_and_auth_gate_recognize_token(monkeypatch):
    from trackio import server

    sub = _user()
    token, _ = auth_store.create_api_token(sub, "t")
    request = _request({"cookie": f"trackio_write_token={token}"})
    status = server.get_run_mutation_status(request)
    assert status["allowed"] is True
    assert status["admin"] is False
    assert status["session"] is False
    assert status["user"] == "Alice"

    assert server._has_server_access_token(_token_request(token))
    assert server._has_server_access_token(_token_request(server.write_token))
    assert not server._has_server_access_token(_token_request("trk_nope"))
    assert not server._has_server_access_token(_request())
