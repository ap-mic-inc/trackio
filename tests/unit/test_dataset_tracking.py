import sqlite3
import sys
import types

import pytest

import trackio
from trackio import dataset_tracking
from trackio.sqlite_storage import SQLiteStorage


class FakeBuilder:
    def __init__(self, repo_id, sha, config="default"):
        self.repo_id = repo_id
        self.hash = sha
        self.config = types.SimpleNamespace(name=config)


@pytest.fixture
def fake_datasets(monkeypatch):
    """A stand-in for the `datasets` package whose load_dataset looks up
    load_dataset_builder at call time, like the real one."""
    load_module = types.ModuleType("datasets.load")
    calls = []

    def load_dataset_builder(path, name=None, revision=None, data_files=None, **_):
        calls.append(path)
        if data_files is not None:
            return FakeBuilder(None, "local-hash")
        sha = {"main": "sha-main", "v2": "sha-v2"}[revision or "main"]
        return FakeBuilder(path, sha, config=name or "default")

    def load_dataset(path, **kwargs):
        return load_module.load_dataset_builder(path, **kwargs)

    load_module.load_dataset_builder = load_dataset_builder
    load_module.load_dataset = load_dataset
    package = types.ModuleType("datasets")
    package.load = load_module
    package.load_dataset = load_dataset
    monkeypatch.setitem(sys.modules, "datasets", package)
    monkeypatch.setitem(sys.modules, "datasets.load", load_module)
    monkeypatch.setattr(dataset_tracking, "_installed", False)
    return package


def _links(project):
    with sqlite3.connect(SQLiteStorage.get_project_db_path(project)) as conn:
        try:
            return conn.execute(
                "SELECT run_name, direction FROM run_artifact_links ORDER BY id"
            ).fetchall()
        except sqlite3.OperationalError:
            return []


def test_hub_datasets_become_input_artifacts(temp_dir, fake_datasets):
    from datasets import load_dataset

    trackio.init(project="ds", name="train-a", auto_log_gpu=False, auto_log_cpu=False)
    load_dataset("org/corpus", split="train")
    load_dataset("org/corpus", split="validation")
    load_dataset("csv", data_files="local.csv")
    trackio.finish()

    trackio.init(project="ds", name="train-b", auto_log_gpu=False, auto_log_cpu=False)
    load_dataset("org/corpus", revision="v2")
    load_dataset("org/corpus", name="subset")
    trackio.finish()

    runs = {r["name"]: r for r in SQLiteStorage.get_run_records("ds")}
    inputs = {
        name: [
            (a["name"], a["version"])
            for a in SQLiteStorage.get_run_artifacts("ds", name, run_id=run["id"])[
                "input"
            ]
        ]
        for name, run in runs.items()
    }
    assert inputs["train-a"] == [("hf-org--corpus", 0)]
    assert sorted(inputs["train-b"]) == [
        ("hf-org--corpus", 1),
        ("hf-org--corpus--subset", 0),
    ]
    assert all(direction == "input" for _, direction in _links("ds"))

    manifest = SQLiteStorage.get_artifact_manifest("ds", "hf-org--corpus", "v1")
    assert manifest["manifest"][0]["ref"] == "hf://datasets/org/corpus@sha-v2"
    assert manifest["metadata"]["revision"] == "sha-v2"
    assert manifest["producer_run_name"] is None


def test_tracking_can_be_disabled(temp_dir, fake_datasets, monkeypatch):
    from datasets import load_dataset

    monkeypatch.setenv("TRACKIO_TRACK_DATASETS", "0")
    trackio.init(project="ds-off", auto_log_gpu=False, auto_log_cpu=False)
    load_dataset("org/corpus")
    trackio.finish()
    assert _links("ds-off") == []


def test_should_track_resolution(monkeypatch):
    monkeypatch.delenv("TRACKIO_TRACK_DATASETS", raising=False)
    monkeypatch.delitem(sys.modules, "datasets", raising=False)
    assert dataset_tracking.should_track(None) is False
    assert dataset_tracking.should_track(True) is True
    monkeypatch.setenv("TRACKIO_TRACK_DATASETS", "1")
    assert dataset_tracking.should_track(None) is True
    assert dataset_tracking.should_track(False) is False
    monkeypatch.setenv("TRACKIO_TRACK_DATASETS", "off")
    monkeypatch.setitem(sys.modules, "datasets", types.ModuleType("datasets"))
    assert dataset_tracking.should_track(None) is False
    monkeypatch.delenv("TRACKIO_TRACK_DATASETS")
    assert dataset_tracking.should_track(None) is True


def test_artifact_names_are_valid():
    assert dataset_tracking.artifact_name("org/name") == "hf-org--name"
    assert dataset_tracking.artifact_name("org/name", "en") == "hf-org--name--en"
    assert dataset_tracking.artifact_name("org/na me", "a/b") == "hf-org--na-me--a-b"
    assert (
        dataset_tracking.reference_uri("org/name", "refs/convert/parquet")
        == "hf://datasets/org/name@refs%2Fconvert%2Fparquet"
    )


def test_recording_failure_does_not_break_loading(
    temp_dir, fake_datasets, monkeypatch, capsys
):
    from datasets import load_dataset

    def boom(*args, **kwargs):
        raise RuntimeError("hub unreachable")

    monkeypatch.setattr(dataset_tracking, "record_hub_dataset", boom)
    monkeypatch.setattr(dataset_tracking, "_warned", False)
    trackio.init(project="ds-err", auto_log_gpu=False, auto_log_cpu=False)
    builder = load_dataset("org/corpus")
    trackio.finish()
    assert builder.repo_id == "org/corpus"
    assert "could not record dataset" in capsys.readouterr().out


def test_artifact_without_producer_creates_no_link(temp_dir):
    run = trackio.init(project="noprod", auto_log_gpu=False, auto_log_cpu=False)
    artifact = trackio.Artifact(name="ref-only", type="dataset")
    artifact.add_reference("https://example.com/data.json", checksum=False)
    run.log_artifact(artifact, as_output=False)
    trackio.finish()
    assert _links("noprod") == []
