import trackio
from trackio import storage_usage, utils
from trackio.sqlite_storage import SQLiteStorage


def test_project_usage_splits_categories(temp_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "trace_sessions_root", lambda: tmp_path / "traces")
    SQLiteStorage.log(project="big", run="r", metrics={"loss": 1.0})
    SQLiteStorage.log(project="small", run="r", metrics={"loss": 1.0})

    media = utils.project_media_dir("big")
    (media / "files").mkdir(parents=True)
    (media / "files" / "config.yaml").write_bytes(b"x" * 10)
    (media / "run" / "0").mkdir(parents=True)
    (media / "run" / "0" / "img.png").write_bytes(b"x" * 20)
    blobs = utils.project_artifacts_dir("big") / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "abc").write_bytes(b"x" * 300)
    traces = tmp_path / "traces" / "big"
    traces.mkdir(parents=True)
    (traces / "t.jsonl").write_bytes(b"x" * 4)

    usage = storage_usage.project_usage("big")
    assert usage["files"] == {"bytes": 10, "files": 1}
    assert usage["media"] == {"bytes": 20, "files": 1}
    assert usage["artifacts"] == {"bytes": 300, "files": 1}
    assert usage["traces"] == {"bytes": 4, "files": 1}
    assert usage["database"]["bytes"] > 0
    assert usage["total"] == sum(usage[c]["bytes"] for c in storage_usage.CATEGORIES)

    report = storage_usage.storage_usage()
    assert [p["project"] for p in report["projects"]] == ["big", "small"]
    assert report["total"] == sum(p["total"] for p in report["projects"])
    assert report["disk"]["total"] >= report["disk"]["free"] > 0


def test_server_endpoint_is_registered():
    from trackio import server

    assert server._api_registry()["get_storage_usage"] is server.get_storage_usage
    assert trackio.__version__
