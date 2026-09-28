import sqlite3
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from trackio.asgi_app import create_trackio_starlette_app
from trackio.server import _api_registry
from trackio.sqlite_storage import SQLiteStorage


def test_status_preserves_identity_latest_step_and_numeric_tail(temp_dir):
    SQLiteStorage.bulk_log(
        "status",
        "same-name",
        [
            {"loss": 9, "old": 1},
            {"loss": 4, "flag": True},
            {"loss": 2, "media": {"x": 1}},
        ],
        steps=[100, 8, 3],
        timestamps=[
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:01:00+00:00",
            "2026-01-01T00:01:00+00:00",
        ],
        run_id="first",
    )
    SQLiteStorage.log("status", "same-name", {"loss": 7}, run_id="second")
    runs = {
        run["id"]: run for run in SQLiteStorage.get_run_status("status", tail_rows=2)
    }
    assert set(runs) == {"first", "second"}
    assert runs["first"]["last_step"] == 3
    assert runs["first"]["first_timestamp"] == "2026-01-01T00:00:00+00:00"
    assert runs["first"]["tail_first_step"] == 8
    assert runs["first"]["metrics"] == {
        "loss": {
            "last": 2,
            "prev": 4,
            "step": 3,
            "timestamp": "2026-01-01T00:01:00+00:00",
        }
    }
    assert runs["second"]["metrics"]["loss"]["last"] == 7


def test_status_includes_config_and_artifact_only_runs(temp_dir):
    db = SQLiteStorage.init_db("empty-runs")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO configs (run_id, run_name, config, created_at) VALUES (?, ?, ?, ?)",
            ("waiting", "waiting", "{}", "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO run_artifact_links (id, run_id, run_name, artifact_version_id, direction, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                "artifact",
                "artifact",
                "version",
                "input",
                "2026-01-01T00:00:00+00:00",
            ),
        )
    runs = SQLiteStorage.get_run_status("empty-runs")
    assert {run["id"] for run in runs} == {"waiting", "artifact"}
    assert all(run["last_timestamp"] is None and run["metrics"] == {} for run in runs)


def test_status_legacy_and_invalid_metric_records(temp_dir):
    db = SQLiteStorage.get_project_db_path("legacy-status")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE metrics (id INTEGER PRIMARY KEY, run_name TEXT, timestamp TEXT, step INTEGER, metrics TEXT)"
        )
        conn.executemany(
            "INSERT INTO metrics VALUES (?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "legacy",
                    "2026-01-01T00:00:00+00:00",
                    0,
                    '{"loss": 1, "bad": 1e400, "flag": true}',
                ),
                (2, "legacy", "2026-01-01T00:01:00+00:00", 1, "broken"),
                (
                    3,
                    "legacy",
                    "2026-01-01T00:02:00+00:00",
                    2,
                    '{"loss": 0.5, "flag": true}',
                ),
                (4, "legacy", "2026-01-01T00:03:00+00:00", 3, "[]"),
            ],
        )
    run = SQLiteStorage.get_run_status("legacy-status")[0]
    assert run["id"] == "legacy"
    assert run["last_step"] == 3
    assert set(run["metrics"]) == {"loss"}
    assert run["metrics"]["loss"]["last"] == 0.5


def test_status_missing_project_does_not_create_database(temp_dir):
    assert SQLiteStorage.get_run_status("absent") == []
    assert not SQLiteStorage.get_project_db_path("absent").exists()


@pytest.mark.parametrize("tail_rows", [0, -1, 501])
def test_status_rejects_unbounded_tail(temp_dir, tail_rows):
    with pytest.raises(ValueError):
        SQLiteStorage.get_run_status("absent", tail_rows)


def test_status_http_contract(temp_dir):
    SQLiteStorage.log("status", "run", {"loss": 0.25})
    app = create_trackio_starlette_app([], _api_registry())
    with TestClient(app) as client:
        response = client.post("/api/get_run_status", json={"project": "status"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert datetime.fromisoformat(data["server_time"]).tzinfo is not None
    assert data["tail_rows"] == 50
    assert data["runs"][0]["metrics"]["loss"]["last"] == 0.25
